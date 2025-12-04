"""High-level orchestrator for the PyP2P client."""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from typing import Dict, Optional

from .cli import CommandLineInterface
from .config import ClientSettings
from .message_router import MessageRouter
from .peer_connection import PeerConnection
from .peer_server import PeerServer
from .peer_table import PeerTable
from .rendezvous_connection import RendezvousClient, RendezvousError
from .state import ClientRuntimeState, PeerInfo


logger = logging.getLogger(__name__)


class P2PClient:
    """Coordena registro no rendezvous, conexões TCP e CLI."""

    def __init__(self, settings: Optional[ClientSettings] = None) -> None:
        self.settings = settings or ClientSettings()
        self.state = ClientRuntimeState()
        self.peer_table = PeerTable()
        self.rendezvous = RendezvousClient(self.settings)
        self.router = MessageRouter(self.peer_table, self.state)
        self.cli = CommandLineInterface(self.router, self.peer_table, p2p_client=self)
        self.connections: Dict[str, PeerConnection] = {}
        self.peer_server = PeerServer(self.settings, self.peer_table, self._handle_inbound_socket)
        self._running = False
        self._discovery_thread: Optional[threading.Thread] = None
        self._discovery_stop = threading.Event()
        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnect_stop = threading.Event()

        # Setar o roteador com as conexões e configs
        self.router.set_local_peer_id(self.settings.peer_id)
        self.router.set_connections(self.connections)
        self.router.set_message_callback(self._on_message_received)

    def start(self) -> None:
        """
        Passos planejados:
        1. Carregar/validar configuração.
        2. Registrar no rendezvous e iniciar ciclo de descoberta.
        3. Subir TCP listener + reconciliação de peers.
        4. Iniciar CLI, keep-alive e observabilidade.
        5. Permanecer ativo até `/quit` ou sinal do sistema.
        """

        if self._running:
            logger.debug("Cliente já iniciado; ignorando chamada extra.")
            return

        self._running = True
        logger.info("Inicializando cliente PyP2P para peer %s", self.settings.peer_id)
        try:
            self.peer_server.start()
        except OSError as exc:
            self._running = False
            logger.error("Não foi possível iniciar PeerServer: %s", exc)
            raise
        try:
            self.rendezvous.register(port=self.settings.listen_port, ttl=self.settings.ttl_seconds)
        except RendezvousError as exc:
            self._running = False
            self.peer_server.stop()
            logger.error("Falha ao registrar no rendezvous: %s", exc)
            raise

        self.cli.start()
        self.router.start_ack_checker()
        self.discover_once()
        self.reconcile_peer_connections()  # Conecta imediatamente aos peers descobertos
        self._start_discovery_worker()
        self._start_reconnect_worker()

    def shutdown(self) -> None:
        if not self._running:
            return
        logger.info("Encerrando cliente PyP2P...")
        self._stop_discovery_worker()
        self._stop_reconnect_worker()
        self.router.stop_ack_checker()
        
        # Manda BYE pra todos os peers
        for peer_id in list(self.connections.keys()):
            self.router.send_bye(peer_id, "Encerrando cliente")
        
        # Espera respostas do BYE
        time.sleep(0.5)
        
        for connection in list(self.connections.values()):
            connection.close()
        self.connections.clear()
        self.peer_server.stop()
        self.cli.stop()
        try:
            self.rendezvous.unregister(port=self.settings.listen_port)
        except RendezvousError as exc:
            logger.warning("Falha ao realizar UNREGISTER: %s", exc)
        self._running = False

    def discover_once(self) -> None:
        """Executa uma iteração de descoberta e atualiza a PeerTable."""

        try:
            peers = self.rendezvous.discover_peers()
        except RendezvousError as exc:
            logger.warning("DISCOVER falhou: %s", exc)
            return

        seen_ids = set()
        new_peers = []
        updated_peers = []
        
        for peer in peers:
            if peer.peer_id == self.settings.peer_id:
                continue
            seen_ids.add(peer.peer_id)
            is_new = self.peer_table.upsert_peer(peer)
            if is_new:
                new_peers.append(peer)
                logger.info("Novo peer descoberto: %s (%s:%d)", peer.peer_id, peer.address, peer.port)
            else:
                updated_peers.append(peer)
        
        if seen_ids:
            self.peer_table.mark_missing_as_stale(seen_ids, stale_after=self.settings.discovery_interval * 2)
        
        if new_peers:
            logger.info("DISCOVER: %d novos peers, %d atualizados", len(new_peers), len(updated_peers))
            # Tenta conectar imediatamente aos novos peers descobertos
            for peer in new_peers:
                if peer.peer_id not in self.connections:
                    self.connect_to_peer(peer)
        else:
            logger.debug("DISCOVER: %d peers atualizados, nenhum novo", len(updated_peers))
        
        logger.debug("PeerTable sincronizada: %s", self.peer_table.stats())

    def _handle_inbound_socket(self, peer: PeerInfo, conn: socket.socket) -> None:
        """Recebe socket aceito pelo PeerServer e inicia o PeerConnection.
        
        Se já existe uma conexão com este peer (ele já conectou ou nós conectamos nele),
        a nova conexão é rejeitada para evitar duplicatas.
        """
        # Verifica se já existe conexão com este peer
        if peer.peer_id in self.connections:
            logger.info("Conexão inbound de %s rejeitada: já existe conexão ativa", peer.peer_id)
            try:
                # Envia uma mensagem de rejeição antes de fechar
                reject_msg = {
                    "type": "HELLO_REJECT",
                    "reason": "Conexão duplicada - já existe conexão ativa",
                    "peer_id": self.settings.peer_id
                }
                conn.sendall((json.dumps(reject_msg) + "\n").encode("utf-8"))
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return
        
        self.peer_table.upsert_peer(peer)
        connection = PeerConnection.from_inbound(
            self.settings,
            peer,
            conn,
            on_message=self._on_connection_message,
            on_closed=self._on_connection_closed,
        )
        self.connections[peer.peer_id] = connection
        connection.start_reader()
        logger.info("Conexão inbound aceita de %s", peer.peer_id)

    def _on_connection_message(self, connection: PeerConnection, message: dict) -> None:
        self.router.handle_incoming(message, connection)

    def _on_connection_closed(self, connection: PeerConnection) -> None:
        self.connections.pop(connection.peer.peer_id, None)
        self.peer_table.mark_stale(connection.peer.peer_id)

    def _on_message_received(self, src: str, dst: str, payload: str) -> None:
        """Callback chamado quando uma mensagem é recebida."""
        # Exibe na CLI
        if dst == "*":
            print(f"\n[BROADCAST {src}] {payload}")
        elif dst.startswith("#"):
            print(f"\n[{dst} {src}] {payload}")
        else:
            print(f"\n[{src}] {payload}")
        print(self.cli.prompt, end="", flush=True)

    def _start_discovery_worker(self) -> None:
        if self._discovery_thread and self._discovery_thread.is_alive():
            return

        def _loop() -> None:
            while not self._discovery_stop.wait(self.settings.discovery_interval):
                self.discover_once()

        self._discovery_stop.clear()
        self._discovery_thread = threading.Thread(target=_loop, name="discovery", daemon=True)
        self._discovery_thread.start()

    def _stop_discovery_worker(self) -> None:
        if not self._discovery_thread:
            return
        self._discovery_stop.set()
        self._discovery_thread.join(timeout=2)
        self._discovery_thread = None

    def _start_reconnect_worker(self) -> None:
        """Inicia worker que tenta reconectar com peers periodicamente."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return

        def _loop() -> None:
            while not self._reconnect_stop.wait(30.0):  # Tenta a cada 30 segundos
                self.reconcile_peer_connections()

        self._reconnect_stop.clear()
        self._reconnect_thread = threading.Thread(target=_loop, name="reconnect", daemon=True)
        self._reconnect_thread.start()

    def _stop_reconnect_worker(self) -> None:
        if not self._reconnect_thread:
            return
        self._reconnect_stop.set()
        self._reconnect_thread.join(timeout=2)
        self._reconnect_thread = None

    def connect_to_peer(self, peer: PeerInfo) -> bool:
        """Estabelece conexão outbound com peer.
        
        Não conecta se já existir uma conexão (inbound ou outbound) com este peer.
        """
        if peer.peer_id in self.connections:
            existing = self.connections[peer.peer_id]
            conn_type = "inbound" if not existing.is_outbound else "outbound"
            logger.debug("Já conectado a %s (conexão %s)", peer.peer_id, conn_type)
            return True
        
        try:
            connection = PeerConnection.connect_outbound(self.settings, peer,
            on_message=self._on_connection_message, on_closed=self._on_connection_closed)

            # Verificação extra de race condition
            if peer.peer_id in self.connections:
                logger.info("Conexão outbound com %s cancelada: conexão inbound chegou primeiro", peer.peer_id)
                connection.close()
                return True

            self.connections[peer.peer_id] = connection
            connection.start_reader()

            logger.info("Conectado outbound com %s", peer.peer_id)
            return True
        except Exception as exc:
            logger.warning("Falha ao conectar com %s: %s", peer.peer_id, exc)
            return False
        
    def reconcile_peer_connections(self) -> None:
        """Tenta conectar com peers descobertos que não estão conectados.
        
        Implementa backoff exponencial para tentativas de reconexão.
        """
        known_peers = list(self.peer_table.all())
        connected_count = 0
        attempted_count = 0

        for peer in known_peers:
            if peer.peer_id == self.settings.peer_id:
                continue
            if peer.peer_id in self.connections:
                continue
            if not peer.address or not peer.port:
                continue
            
            # Verifica o max de tentativas de reconexao
            if peer.reconnect_attempts >= self.settings.max_reconnect_attempts:
                logger.debug("Peer %s atingiu máximo de tentativas (%d)", 
                           peer.peer_id, self.settings.max_reconnect_attempts)
                continue
                
            # Calcula o delay de backoff
            backoff_delay = self.settings.reconnect_backoff_base ** peer.reconnect_attempts
            last_attempt = peer.last_connection_attempt or 0
            
            if time.time() - last_attempt < backoff_delay:
                continue
                
            logger.debug("Tentando conectar com %s (%s:%s) - tentativa %d", 
                        peer.peer_id, peer.address, peer.port, peer.reconnect_attempts + 1)
            attempted_count += 1

            # Atualiza o tracking de tentativas
            peer.last_connection_attempt = time.time()
            peer.reconnect_attempts += 1
            self.peer_table.upsert_peer(peer)

            if self.connect_to_peer(peer):
                # Reseta tentativas quando funciona
                peer.reconnect_attempts = 0
                peer.status = "CONNECTED"
                self.peer_table.upsert_peer(peer)
                connected_count += 1
        
        if attempted_count > 0:
            logger.info("Reconciliação: %d tentativas, %d novas conexões", attempted_count, connected_count)

    def get_connection_metrics(self) -> dict:
        metrics = {
            "total_connections": len(self.connections),
            "connections": {},
            "summary": {
                "avg_rtt": 0,
                "healthy_connections": 0
            }
        }

        total_rtt = 0
        count_rtt = 0

        for peer_id, connection in self.connections.items():
            conn_metrics = connection.get_metrics()
            metrics["connections"][peer_id] = conn_metrics

            if conn_metrics["avg_rtt"] > 0:
                total_rtt += conn_metrics["avg_rtt"]
                count_rtt += 1
                metrics["summary"]["healthy_connections"] += 1
            
        if count_rtt > 0:
            metrics["summary"]["avg_rtt"] = total_rtt / count_rtt
        
        return metrics