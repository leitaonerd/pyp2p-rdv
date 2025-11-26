"""Command-line interface loop placeholder."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from .message_router import MessageRouter
from .peer_table import PeerTable

logger = logging.getLogger(__name__)

class CommandLineInterface:
    """Responsável pelos comandos `/peers`, `/msg`, `/pub`, etc."""

    def __init__(
        self,
        router: MessageRouter,
        peer_table: PeerTable,
        p2p_client=None,
        prompt: str = "pyp2p> ",
    ) -> None:
        self.router = router
        self.peer_table = peer_table
        self.p2p_client = p2p_client
        self.prompt = prompt
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._output_callback: Optional[Callable[[str], None]] = None

    def attach_output(self, callback: Callable[[str], None]) -> None:
        """Permite redirecionar mensagens da CLI para testes/UI."""

        self._output_callback = callback

    def start(self) -> None:
        """Inicia o loop interativo em uma thread dedicada.

        TODOs principais:
        - Implementar parser real (provavelmente `cmd.Cmd` ou `prompt_toolkit`).
        - Garantir que o loop não bloqueie o recebimento de mensagens.
        - Exibir ajuda contextual (`/help`).
        - Integrar níveis de log (comando `/log`).
        """

        if self._thread and self._thread.is_alive():
            return

        def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    user_input = input(self.prompt)
                except (EOFError, KeyboardInterrupt):
                    break
                self._handle_command(user_input.strip())

        self._stop_event.clear()
        self._thread = threading.Thread(target=_loop, name="cli", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2)
        self._thread = None

    def _handle_command(self, raw_command: str) -> None:
        if not raw_command or not raw_command.startswith("/"):
            return
        
        parts = raw_command.split()
        command = parts[0].lower()

        try:
            if command == "/peers":
                self._cmd_peers(parts[1:])
            elif command == "/msg":
                self._cmd_msg(parts[1:])
            elif command == "/pub":
                self._cmd_pub(parts[1:])
            elif command == "/conn":
                self._cmd_conn()
            elif command == "/rtt":
                self._cmd_rtt()
            elif command == "/reconnect":
                self._cmd_reconnect()
            elif command == "/log":
                self._cmd_log(parts[1:])
            elif command == "/quit":
                self._cmd_quit()
            elif command == "/help":
                self._cmd_help()
            else:
                self._emit(f"Comando desconhecido: {command}")

        except Exception as exc:
            self._emit(f"Erro executando {command}: {exc}")


        self._emit(f"[CLI] Comando recebido (stub): {raw_command}")

    def _cmd_peers(self, args: list) -> None:
        filter_arg = args[0] if args else None

        peers = self.peer_table.all()
        if not peers:
            self._emit("Nenhum peer conhecido")
            return
        
        if filter_arg == "*":
            filtered_peers = peers
            title = "TODOS OS PEERS"
        elif filter_arg and filter_arg.startswith("#"):
            namespace = filter_arg[1:]
            filtered_peers = [p for p in peers if hasattr(p, "namespace") and p.namespace == namespace]
            title = f"PEERS DO NAMESPACE #{namespace}"
        else:
            filtered_peers = peers
            title = "PEERS CONHECIDOS"
        
        if not filtered_peers:
            self._emit(f"Nenhum peer encontrado para o filtro: {filter_arg}")
            return
        
        connected_count = 0
        for peer in filtered_peers:
            status_icon =  "Connected" if getattr(peer, "status", "") == "CONNECTED" else "Not connected"
            peer_line = f"  {peer.peer_id} {status_icon}"

            if hasattr(peer, "address") and peer.address:
                peer_line += f" | {peer.address}:{getattr(peer, "port", "?")}"
            if hasattr(peer, "namespace") and peer.namespace:
                peer_line += f" | #{peer.namespace}"
            if hasattr(peer, "status"):
                peer_line += f" | {peer.status}"
                
            self._emit(peer_line)
            
            if getattr(peer, "status", "") == "CONNECTED":
                connected_count += 1
            
        self._emit(f"\nTotal: {len(filtered_peers)} peers, {connected_count} conectados")
    
    def _cmd_msg(self, args: list) -> None:
        if len(args) < 2:
            self._emit("Uso: /msg <peer_id> <mensagem>")
            self._emit("Exemplo: /msg alice@CIC Olá, como vai?")
            return

        peer_id = args[0]
        message_text = " ".join(args[1:])

        peers = self.peer_table.all()
        target_peer = next((p for p in peers if p.peer_id == peer_id), None)
        
        if not target_peer:
            self._emit(f"Erro: Peer '{peer_id}' não encontrado")
            self._emit("Use /peers para ver peers disponíveis")
            return

        self._emit(f"[{peer_id}] {message_text}")
        self._emit("Mensagem enfileirada")

        # TODO: Implementar com self.router.send_direct_message(peer_id, message_text)

    def _cmd_pub(self, args: list) -> None:
        if len(args) < 2:
            self._emit("Uso: /pub <destino> <mensagem>")
            self._emit("  Destinos:")
            self._emit("    *         - Broadcast para todos os peers")
            self._emit("    #<namespace> - Apenas para peers do namespace")
            return

        destination = args[0]
        message_text = " ".join(args[1:])

        if destination == "*":
            peers = self.peer_table.all()
            target_count = len([p for p in peers if p.peer_id != getattr(self, "local_peer_id", "")])
            self._emit(f"[BROADCAST] {message_text}")
            self._emit(f"Enviando para {target_count} peers")
            
        elif destination.startswith("#"):
            namespace = destination[1:]
            peers = self.peer_table.all()
            namespace_peers = [p for p in peers if hasattr(p, "namespace") and p.namespace == namespace]
            target_count = len(namespace_peers)
            
            self._emit(f"[#{namespace}] {message_text}")
            self._emit(f"Enviando para {target_count} peers no namespace #{namespace}")
            
        else:
            self._emit("Erro: Destino deve ser '*' ou '#<namespace>'")
            return

        # TODO: Implementar com self.router.send_public_message(destination, message_text)

    def _cmd_conn(self) -> None:
        if not self.p2p_client:
            self._emit("Funcionalidade /conn não disponível")
            return

        try:
            metrics = self.p2p_client.get_connection_metrics()

            self._emit("\n=== CONEXÕES ATIVAS ===")
            self._emit(f"Total: {metrics["total_connections"]} conexões")

            if metrics["total_connections"] == 0:
                self._emit("Nenhuma conexão ativa no momento")
                return

            if metrics["summary"]["healthy_connections"] > 0:
                self._emit(f"RTT médio: {metrics["summary"]["avg_rtt"]:.3f}s")
                self._emit(f"Conexões saudáveis: {metrics["summary"]["healthy_connections"]}")

            self._emit("\nDetalhes por peer:")
            self._emit("Peer             Tipo    RTT Médio   Amostras     Status")

            for peer_id, conn_metrics in metrics["connections"].items():
                conn_type = "OUT" if conn_metrics["is_outbound"] else "IN"
                rtt_display = f"{conn_metrics["avg_rtt"]:.3f}s" if conn_metrics["avg_rtt"] > 0 else "N/A"
                samples = conn_metrics["rtt_samples"]
                status = "Connected" if conn_metrics["active"] else "Not connected"

                self._emit(f"{peer_id:15}  {conn_type:6}   {rtt_display:10}   {samples:2d}        {status}")

        except Exception as exc:
            self._emit(f"Erro ao obter métricas: {exc}")

    def _cmd_rtt(self) -> None:
        if not self.p2p_client:
            self._emit("Funcionalidade /rtt não disponível")
            return

        try:
            metrics = self.p2p_client.get_connection_metrics()

            self._emit("\n=== LATÊNCIA (RTT) ===")

            if metrics['total_connections'] == 0:
                self._emit("Nenhuma conexão ativa para medir RTT")
                return

            connections_with_rtt = [(peer_id, conn_metrics) for peer_id, conn_metrics in metrics["connections"].items()
                if conn_metrics["rtt_samples"] > 0]

            if not connections_with_rtt:
                self._emit("Nenhuma métrica RTT disponível ainda")
                self._emit("Aguardando troca de PING/PONG...")
                return

            self._emit("Peer              RTT Médio    Amostras    Atualização      Qualidade")

            for peer_id, conn_metrics in connections_with_rtt:
                rtt = conn_metrics["avg_rtt"]
                samples = conn_metrics["rtt_samples"]

                last_pong = conn_metrics.get("last_pong")
                if last_pong:
                    time_str = "há poucos segundos"
                else:
                    time_str = "nunca"

                if rtt < 0.1:
                    quality = "Excelente"
                elif rtt < 0.3:
                    quality = "Boa" 
                elif rtt < 1.0:
                    quality = "Aceitável"
                else:
                    quality = "Lenta"

                self._emit(f"{peer_id:15} {rtt:8.3f}s     {samples:6d}         {time_str:15} {quality}")

            if metrics["summary"]["avg_rtt"] > 0:
                self._emit(f"\nRTT médio geral: {metrics["summary"]["avg_rtt"]:.3f}s")
                self._emit(f"Conexões com métricas: {len(connections_with_rtt)}/{metrics["total_connections"]}")

        except AttributeError as exc:
            self._emit(f"Método get_connection_metrics não encontrado: {exc}")
        except Exception as exc:
            self._emit(f"Erro ao obter métricas RTT: {exc}")

    def _cmd_reconnect(self) -> None:
        if not self.p2p_client:
            self._emit("Funcionalidade /reconnect não disponível")
            return

        self._emit("Forçando reconciliação de conexões...")
        
        # TODO: Implementar self.p2p_client.force_reconciliation()
        self._emit("Reconciliação solicitada")
        self._emit("Funcionalidade em desenvolvimento")

    def _cmd_log(self, args: list) -> None:
        if not args:
            current_level = logging.getLevelName(logger.getEffectiveLevel())
            self._emit(f"Nível de log atual: {current_level}")
            self._emit("Uso: /log <DEBUG|INFO|WARNING|ERROR>")
            return

        level_name = args[0].upper()
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR
        }

        if level_name not in level_map:
            self._emit(f"Nível inválido: {level_name}. Use: {", ".join(level_map.keys())}")
            return

        logging.getLogger().setLevel(level_map[level_name])
        logger.setLevel(level_map[level_name])
        self._emit(f"Nível de log alterado para: {level_name}")

    def _cmd_quit(self) -> None:
        self._emit("Encerrando cliente PyP2P...")
        self.stop()

        if self.p2p_client:
            self.p2p_client.shutdown()

    def _cmd_help(self) -> None:
        help_text = """

PEERS & CONEXÕES:
  /peers [*|#ns]    - Listar peers (todos ou por namespace)
  /conn             - Mostrar conexões ativas
  /rtt              - Exibir latência (RTT) por peer
  /reconnect        - Forçar reconciliação de conexões

MENSAGENS:
  /msg <peer> <msg> - Mensagem direta para peer
  /pub * <msg>      - Broadcast para todos os peers
  /pub #<ns> <msg>  - Mensagem para namespace

SISTEMA:
  /log <nível>      - Ajustar nível de log
  /help             - Mostrar esta ajuda
  /quit             - Encerrar aplicação

        """
        self._emit(help_text)

    def _emit(self, message: str) -> None:
        if self._output_callback:
            self._output_callback(message)
        else:
            print(message)
