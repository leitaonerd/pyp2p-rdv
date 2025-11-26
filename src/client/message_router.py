"""Routing helpers for SEND/PUB/BYE."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Dict, List, Optional
from uuid import uuid4

from .peer_table import PeerTable
from .state import ClientRuntimeState, MessageRecord

if TYPE_CHECKING:
    from .peer_connection import PeerConnection

logger = logging.getLogger(__name__)

# Timeout for ACK in seconds
ACK_TIMEOUT_SECONDS = 5.0


class MessageRouter:
    """Entrega mensagens para os peers conectados.

    Responsabilidades:
    - Gerenciar pedidos de ACK e timeouts (5s) com alertas nos logs.
    - Tratar PUB para ``*`` e ``#namespace`` evitando duplicidades.
    - Emitir eventos para o CLI (mensagens recebidas e status de entrega).
    """

    def __init__(self, peer_table: PeerTable, state: ClientRuntimeState) -> None:
        self.peer_table = peer_table
        self.state = state
        self._connections: Dict[str, "PeerConnection"] = {}
        self._local_peer_id: str = ""
        self._pending_acks: Dict[str, MessageRecord] = {}
        self._ack_lock = threading.Lock()
        self._on_message_received: Optional[Callable[[str, str, str], None]] = None
        self._ack_checker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def set_local_peer_id(self, peer_id: str) -> None:
        """Define o peer_id local para uso nos campos 'src'."""
        self._local_peer_id = peer_id

    def set_connections(self, connections: Dict[str, "PeerConnection"]) -> None:
        """Define referência para o dicionário de conexões ativas."""
        self._connections = connections

    def set_message_callback(self, callback: Callable[[str, str, str], None]) -> None:
        """Define callback para quando mensagem for recebida: callback(src, dst, payload)."""
        self._on_message_received = callback

    def start_ack_checker(self) -> None:
        """Inicia thread que verifica timeouts de ACK."""
        if self._ack_checker_thread and self._ack_checker_thread.is_alive():
            return

        def _check_loop() -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(1.0)
                self._check_ack_timeouts()

        self._stop_event.clear()
        self._ack_checker_thread = threading.Thread(target=_check_loop, name="ack-checker", daemon=True)
        self._ack_checker_thread.start()

    def stop_ack_checker(self) -> None:
        """Para a thread de verificação de ACKs."""
        self._stop_event.set()
        if self._ack_checker_thread and self._ack_checker_thread.is_alive():
            self._ack_checker_thread.join(timeout=2)
        self._ack_checker_thread = None

    def _check_ack_timeouts(self) -> None:
        """Verifica mensagens pendentes que excederam o timeout de ACK."""
        now = datetime.now(timezone.utc)
        expired: List[str] = []

        with self._ack_lock:
            for msg_id, record in self._pending_acks.items():
                elapsed = (now - record.timestamp).total_seconds()
                if elapsed > ACK_TIMEOUT_SECONDS:
                    expired.append(msg_id)

            for msg_id in expired:
                record = self._pending_acks.pop(msg_id)
                record.error = "ACK timeout (5s)"
                logger.warning("[Router] ACK timeout para msg_id=%s dst=%s", msg_id, record.dst)

    def send(self, dst_peer_id: str, payload: str, require_ack: bool = True) -> Optional[MessageRecord]:
        """Envia mensagem SEND para um peer específico."""
        connection = self._connections.get(dst_peer_id)
        if not connection:
            logger.warning("[Router] Peer %s não conectado, não é possível enviar", dst_peer_id)
            return None

        msg_id = str(uuid4())
        now = datetime.now(timezone.utc)

        record = MessageRecord(
            msg_id=msg_id,
            src=self._local_peer_id,
            dst=dst_peer_id,
            payload_preview=payload[:40] if len(payload) > 40 else payload,
            timestamp=now,
        )

        message = {
            "type": "SEND",
            "msg_id": msg_id,
            "src": self._local_peer_id,
            "dst": dst_peer_id,
            "payload": payload,
            "require_ack": require_ack,
            "ttl": 1,
        }

        try:
            connection.send_json(message)
            logger.info("[Router] SEND %s: %s", dst_peer_id, payload[:40])
            self.state.outbound_history.append(record)

            if require_ack:
                with self._ack_lock:
                    self._pending_acks[msg_id] = record

            return record
        except Exception as exc:
            record.error = str(exc)
            logger.error("[Router] Falha ao enviar para %s: %s", dst_peer_id, exc)
            return record

    def publish(self, destination: str, payload: str) -> Dict[str, Optional[MessageRecord]]:
        """Envia PUB para um namespace (#ns) ou broadcast global (*)."""
        results: Dict[str, Optional[MessageRecord]] = {}
        msg_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Determina peers de destino
        if destination == "*":
            target_peers = [p for p in self._connections.keys() if p != self._local_peer_id]
        elif destination.startswith("#"):
            namespace = destination[1:]
            all_peers = self.peer_table.all()
            target_peers = [
                p.peer_id for p in all_peers
                if p.namespace == namespace and p.peer_id in self._connections and p.peer_id != self._local_peer_id
            ]
        else:
            logger.warning("[Router] Destino PUB inválido: %s", destination)
            return results

        for peer_id in target_peers:
            connection = self._connections.get(peer_id)
            if not connection:
                continue

            record = MessageRecord(
                msg_id=f"{msg_id}-{peer_id}",
                src=self._local_peer_id,
                dst=peer_id,
                payload_preview=payload[:40] if len(payload) > 40 else payload,
                timestamp=now,
            )

            message = {
                "type": "PUB",
                "msg_id": msg_id,
                "src": self._local_peer_id,
                "dst": destination,
                "payload": payload,
                "require_ack": False,
                "ttl": 1,
            }

            try:
                connection.send_json(message)
                logger.info("[Router] PUB %s -> %s: %s", destination, peer_id, payload[:40])
                self.state.outbound_history.append(record)
                results[peer_id] = record
            except Exception as exc:
                record.error = str(exc)
                logger.error("[Router] Falha ao enviar PUB para %s: %s", peer_id, exc)
                results[peer_id] = record

        return results

    def send_bye(self, dst_peer_id: str, reason: str = "Encerrando sessão") -> bool:
        """Envia mensagem BYE para um peer."""
        connection = self._connections.get(dst_peer_id)
        if not connection:
            return False

        msg_id = str(uuid4())
        message = {
            "type": "BYE",
            "msg_id": msg_id,
            "src": self._local_peer_id,
            "dst": dst_peer_id,
            "reason": reason,
            "ttl": 1,
        }

        try:
            connection.send_json(message)
            logger.info("[Router] BYE enviado para %s: %s", dst_peer_id, reason)
            return True
        except Exception as exc:
            logger.error("[Router] Falha ao enviar BYE para %s: %s", dst_peer_id, exc)
            return False

    def handle_incoming(self, message: dict, connection: "PeerConnection") -> None:
        """Processa mensagem recebida (SEND, PUB, ACK, BYE, BYE_OK)."""
        msg_type = message.get("type")
        msg_id = message.get("msg_id", "")
        src = message.get("src", "")
        dst = message.get("dst", "")
        payload = message.get("payload", "")

        if msg_type == "SEND":
            self._handle_send(message, connection)
        elif msg_type == "PUB":
            self._handle_pub(message, connection)
        elif msg_type == "ACK":
            self._handle_ack(message)
        elif msg_type == "BYE":
            self._handle_bye(message, connection)
        elif msg_type == "BYE_OK":
            self._handle_bye_ok(message, connection)
        else:
            logger.debug("[Router] Mensagem ignorada tipo=%s", msg_type)

    def _handle_send(self, message: dict, connection: "PeerConnection") -> None:
        """Processa mensagem SEND recebida."""
        msg_id = message.get("msg_id", "")
        src = message.get("src", "")
        dst = message.get("dst", "")
        payload = message.get("payload", "")
        require_ack = message.get("require_ack", True)

        logger.info("[Router] RECV de %s: %s", src, payload[:40] if len(payload) > 40 else payload)

        # Registra no histórico
        record = MessageRecord(
            msg_id=msg_id,
            src=src,
            dst=dst,
            payload_preview=payload[:40] if len(payload) > 40 else payload,
            timestamp=datetime.now(timezone.utc),
        )
        self.state.inbound_history.append(record)

        # Notifica callback (para exibir na CLI)
        if self._on_message_received:
            self._on_message_received(src, dst, payload)

        # Envia ACK se solicitado
        if require_ack:
            self._send_ack(msg_id, connection)

    def _handle_pub(self, message: dict, connection: "PeerConnection") -> None:
        """Processa mensagem PUB recebida."""
        msg_id = message.get("msg_id", "")
        src = message.get("src", "")
        dst = message.get("dst", "")
        payload = message.get("payload", "")

        logger.info("[Router] PUB de %s [%s]: %s", src, dst, payload[:40] if len(payload) > 40 else payload)

        # Registra no histórico
        record = MessageRecord(
            msg_id=msg_id,
            src=src,
            dst=dst,
            payload_preview=payload[:40] if len(payload) > 40 else payload,
            timestamp=datetime.now(timezone.utc),
        )
        self.state.inbound_history.append(record)

        # Notifica callback
        if self._on_message_received:
            self._on_message_received(src, dst, payload)

    def _handle_ack(self, message: dict) -> None:
        """Processa ACK recebido."""
        msg_id = message.get("msg_id", "")

        with self._ack_lock:
            record = self._pending_acks.pop(msg_id, None)

        if record:
            record.acknowledged = True
            record.ack_timestamp = datetime.now(timezone.utc)
            rtt = (record.ack_timestamp - record.timestamp).total_seconds() * 1000
            logger.info("[Router] ACK recebido para msg_id=%s (RTT=%.1fms)", msg_id, rtt)
        else:
            logger.debug("[Router] ACK para msg_id desconhecido: %s", msg_id)

    def _handle_bye(self, message: dict, connection: "PeerConnection") -> None:
        """Processa BYE recebido e envia BYE_OK."""
        msg_id = message.get("msg_id", "")
        src = message.get("src", "")
        reason = message.get("reason", "")

        logger.info("[Router] BYE recebido de %s: %s", src, reason)

        # Envia BYE_OK
        bye_ok = {
            "type": "BYE_OK",
            "msg_id": msg_id,
            "src": self._local_peer_id,
            "dst": src,
            "ttl": 1,
        }

        try:
            connection.send_json(bye_ok)
            logger.info("[Router] BYE_OK enviado para %s", src)
        except Exception as exc:
            logger.warning("[Router] Falha ao enviar BYE_OK: %s", exc)

        # Fecha a conexão após pequeno delay
        threading.Timer(0.5, connection.close).start()

    def _handle_bye_ok(self, message: dict, connection: "PeerConnection") -> None:
        """Processa BYE_OK recebido."""
        src = message.get("src", "")
        logger.info("[Router] BYE_OK recebido de %s", src)
        # Conexão será fechada pelo initiator

    def _send_ack(self, msg_id: str, connection: "PeerConnection") -> None:
        """Envia ACK para uma mensagem recebida."""
        ack = {
            "type": "ACK",
            "msg_id": msg_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ttl": 1,
        }

        try:
            connection.send_json(ack)
            logger.debug("[Router] ACK enviado para msg_id=%s", msg_id)
        except Exception as exc:
            logger.warning("[Router] Falha ao enviar ACK: %s", exc)
