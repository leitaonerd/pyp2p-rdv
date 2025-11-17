"""Abstrações para conexões TCP com outros peers."""
from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Callable, Optional

from .config import ClientSettings
from .state import PeerInfo


logger = logging.getLogger(__name__)
MAX_LINE_BYTES = 32 * 1024


class PeerConnection:
    """Representa uma conexão (inbound ou outbound) com outro peer."""

    def __init__(
        self,
        settings: ClientSettings,
        peer: PeerInfo,
        sock: socket.socket,
        is_outbound: bool,
        on_message: Optional[Callable[["PeerConnection", dict], None]] = None,
        on_closed: Optional[Callable[["PeerConnection"], None]] = None,
    ) -> None:
        self.settings = settings
        self.peer = peer
        self.socket = sock
        self.is_outbound = is_outbound
        self._on_message = on_message
        self._on_closed = on_closed
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @classmethod
    def from_inbound(
        cls,
        settings: ClientSettings,
        peer: PeerInfo,
        sock: socket.socket,
        on_message: Optional[Callable[["PeerConnection", dict], None]] = None,
        on_closed: Optional[Callable[["PeerConnection"], None]] = None,
    ) -> "PeerConnection":
        return cls(settings, peer, sock, is_outbound=False, on_message=on_message, on_closed=on_closed)

    @classmethod
    def connect_outbound(
        cls,
        settings: ClientSettings,
        peer: PeerInfo,
        on_message: Optional[Callable[["PeerConnection", dict], None]] = None,
        on_closed: Optional[Callable[["PeerConnection"], None]] = None,
    ) -> "PeerConnection":
        sock = socket.create_connection((peer.address, peer.port), timeout=settings.rendezvous_timeout)
        connection = cls(settings, peer, sock, is_outbound=True, on_message=on_message, on_closed=on_closed)
        connection.send_json(
            {
                "type": "HELLO",
                "peer_id": settings.peer_id,
                "version": "1.0",
                "features": ["ack"],
                "ttl": 1,
            }
        )
        hello_ok = connection._recv_line()
        try:
            payload = json.loads(hello_ok)
        except json.JSONDecodeError as exc:  # pragma: no cover - handshake failure path
            sock.close()
            raise RuntimeError(f"HELLO_OK inválido recebido de {peer.peer_id}") from exc
        if payload.get("type") != "HELLO_OK":
            sock.close()
            raise RuntimeError(f"Resposta inesperada de {peer.peer_id}: {payload}")
        return connection

    def start_reader(self) -> None:
        if self._reader_thread and self._reader_thread.is_alive():
            return

        def _loop() -> None:
            try:
                while not self._stop_event.is_set():
                    line = self._recv_line()
                    if not line:
                        break
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("[%s] mensagem inválida recebida: %s", self.peer.peer_id, line)
                        continue
                    if self._on_message:
                        self._on_message(self, message)
            finally:
                self.close()

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=_loop, name=f"peer-reader-{self.peer.peer_id}", daemon=True)
        self._reader_thread.start()

    def send_json(self, message: dict) -> None:
        encoded = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_LINE_BYTES:
            raise ValueError("Payload excede 32KiB")
        self._send_raw(encoded)

    def _send_raw(self, data: bytes) -> None:
        try:
            self.socket.sendall(data)
        except OSError as exc:
            logger.warning("[%s] erro ao enviar dados: %s", self.peer.peer_id, exc)
            self.close()

    def _recv_line(self) -> str:
        buf = b""
        self.socket.settimeout(self.settings.extra.get("peer_read_timeout", 10.0))
        while True:
            chunk = self.socket.recv(4096)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_LINE_BYTES:
                raise ValueError("Mensagem maior que o limite permitido")
            if b"\n" in buf:
                line, _ = buf.split(b"\n", 1)
                return line.decode("utf-8", errors="replace")
        return buf.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        finally:
            self.socket.close()
        if self._on_closed:
            self._on_closed(self)
