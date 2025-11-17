"""TCP server responsible for inbound peer connections."""
from __future__ import annotations

import json
import logging
import socket
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from .config import ClientSettings
from .peer_table import PeerTable
from .state import PeerInfo


logger = logging.getLogger(__name__)
MAX_LINE_BYTES = 32 * 1024


class PeerServer:
    """Listens for inbound peer connections and performs HELLO handshake."""

    def __init__(
        self,
        settings: ClientSettings,
        peer_table: PeerTable,
    on_peer_connected: Callable[[PeerInfo, socket.socket], None],
    ) -> None:
        self.settings = settings
        self.peer_table = peer_table
        self.on_peer_connected = on_peer_connected
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._server_socket: Optional[socket.socket] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.settings.listen_host, self.settings.listen_port))
        server.listen(self.settings.extra.get("inbound_backlog", 64))
        self._server_socket = server

        def _loop() -> None:
            logger.info(
                "PeerServer escutando em %s:%s",
                self.settings.listen_host,
                self.settings.listen_port,
            )
            while not self._stop_event.is_set():
                try:
                    server.settimeout(1.0)
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(
                    target=self._handle_connection,
                    args=(conn, addr),
                    name=f"peer-inbound-{addr[0]}:{addr[1]}",
                    daemon=True,
                ).start()

        self._stop_event.clear()
        self._thread = threading.Thread(target=_loop, name="peer-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _handle_connection(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        peer = f"{addr[0]}:{addr[1]}"
        try:
            line = self._recv_line(conn)
            payload = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("[%s] HELLO inválido (JSON)", peer)
            conn.close()
            return
        except ValueError as exc:
            logger.warning("[%s] Erro lendo HELLO: %s", peer, exc)
            conn.close()
            return

        if payload.get("type") != "HELLO":
            logger.warning("[%s] Primeiro pacote não é HELLO: %s", peer, payload)
            conn.close()
            return

        peer_id = payload.get("peer_id")
        if not isinstance(peer_id, str):
            logger.warning("[%s] HELLO sem peer_id", peer)
            conn.close()
            return

        peer_info = PeerInfo(
            peer_id=peer_id,
            address=addr[0],
            port=addr[1],
            namespace=peer_id.split("@")[-1],
            status="CONNECTED",
            last_seen_at=datetime.now(timezone.utc),
            features=list(payload.get("features", [])),
        )
        self.peer_table.upsert_peer(peer_info)

        response = {
            "type": "HELLO_OK",
            "peer_id": self.settings.peer_id,
            "version": payload.get("version", "1.0"),
            "features": payload.get("features", []),
            "ttl": 1,
        }
        try:
            conn.sendall(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
        except OSError:
            logger.debug("[%s] Falha ao enviar HELLO_OK", peer)
            conn.close()
            return

        try:
            self.on_peer_connected(peer_info, conn)
            logger.info("[%s] Handshake HELLO concluído", peer)
        except Exception:
            logger.exception("[%s] Erro ao registrar conexão; fechando socket", peer)
            conn.close()

    def _recv_line(self, conn: socket.socket) -> str:
        conn.settimeout(self.settings.extra.get("peer_handshake_timeout", 5.0))
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_LINE_BYTES:
                raise ValueError("HELLO maior que o limite permitido")
            if b"\n" in buf:
                line, _ = buf.split(b"\n", 1)
                return line.decode("utf-8", errors="replace")
        return buf.decode("utf-8", errors="replace")
