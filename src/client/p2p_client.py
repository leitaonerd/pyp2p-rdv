"""High-level orchestrator for the PyP2P client."""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .cli import CommandLineInterface
from .config import ClientSettings
from .keep_alive import KeepAliveManager
from .message_router import MessageRouter
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
        self.keep_alive = KeepAliveManager(self.settings, self.peer_table)
        self.cli = CommandLineInterface(self.router, self.peer_table)
        self.peer_server = PeerServer(self.settings, self.peer_table, self.register_inbound_peer)
        self._running = False
        self._discovery_thread: Optional[threading.Thread] = None
        self._discovery_stop = threading.Event()

    def start(self) -> None:
        """Fluxo inicial descrito na Seção "Próximos Passos Recomendados".

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

        self.keep_alive.start()
        self.cli.start()
        self.discover_once()
        self._start_discovery_worker()
        # TODO: iniciar reconciliation das conexões TCP.

    def shutdown(self) -> None:
        if not self._running:
            return
        logger.info("Encerrando cliente PyP2P...")
        self._stop_discovery_worker()
        self.peer_server.stop()
        self.keep_alive.stop()
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
        for peer in peers:
            if peer.peer_id == self.settings.peer_id:
                continue
            seen_ids.add(peer.peer_id)
            self.peer_table.upsert_peer(peer)
        if seen_ids:
            self.peer_table.mark_missing_as_stale(seen_ids, stale_after=self.settings.discovery_interval * 2)
        logger.debug("PeerTable sincronizada: %s", self.peer_table.stats())

    def register_inbound_peer(self, peer: PeerInfo) -> None:
        """Hook para quando o servidor TCP aceitar conexão inbound."""

        self.peer_table.upsert_peer(peer)
        # TODO: integrar com MessageRouter/CLI para avisar usuário.

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
