"""Abstrações para conexões TCP com outros peers."""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import uuid4

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
        self._ping_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.last_pong_time = None
        self.rtt_samples = []
        self.ping_interval = settings.ping_interval
        
        # Track pending PINGs by msg_id -> sent_time (float)
        self._pending_pings: dict[str, float] = {}

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
                    try:
                        line = self._recv_line()
                        if not line:
                            # linha vazia ou fechou conexao
                            if self._stop_event.is_set():
                                break
                            continue
                        try:
                            message = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("[%s] mensagem inválida recebida: %s", self.peer.peer_id, line)
                            continue
                        if self._handle_control_message(message):
                            continue
                        if self._on_message:
                            self._on_message(self, message)
                    except socket.timeout:
                        # Timeout is normal - just continue waiting for data
                        continue
                    except OSError as e:
                        if self._stop_event.is_set():
                            break
                        logger.debug("[%s] Erro de socket: %s", self.peer.peer_id, e)
                        break
            finally:
                self.close()

        def _ping_loop() -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(self.ping_interval)

                if not self._stop_event.is_set() and self.is_outbound:
                    self._send_ping()

        self._stop_event.clear()
        self._reader_thread = threading.Thread(target=_loop, name=f"peer-reader-{self.peer.peer_id}", daemon=True)
        self._reader_thread.start()

        if self.is_outbound:
            self._ping_thread = threading.Thread(target=_ping_loop, name=f"peer-ping-{self.peer.peer_id}", daemon=True)
            self._ping_thread.start()

    def _handle_control_message(self, message: dict) -> bool:
        msg_type = message.get("type")

        if msg_type == "PING":
            self._handle_ping(message)
            return True
        elif msg_type == "PONG":
            self._handle_pong(message)
            return True
        elif msg_type == "HELLO":
            # HELLO should only be handled during handshake
            return True
        elif msg_type == "HELLO_OK":
            # HELLO_OK should only be handled during handshake
            return True
        
        return False
    
    def _send_ping(self) -> None:
        """Envia PING com msg_id único e registra tempo de envio."""
        msg_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        ping_msg = {
            "type": "PING",
            "msg_id": msg_id,
            "timestamp": timestamp,
            "ttl": 1
        }
        
        # Guarda o momento de envio pra calcular o RTT
        self._pending_pings[msg_id] = time.time()
        
        # Limpar pings antigos (2 min)
        now = time.time()
        expired = [k for k, v in self._pending_pings.items() if now - v > 120]
        for k in expired:
            del self._pending_pings[k]
        
        try:
            self.send_json(ping_msg)
            logger.debug("[%s] PING enviado (msg_id=%s)", self.peer.peer_id, msg_id[:8])
        except Exception as exc:
            self._pending_pings.pop(msg_id, None)
            logger.debug("[%s] Falha ao enviar PING: %s", self.peer.peer_id, exc)
    
    def _handle_ping(self, message: dict) -> None:
        """Responde ao PING com PONG, ecoando msg_id e timestamp."""
        msg_id = message.get("msg_id", str(uuid4()))
        timestamp = message.get("timestamp", datetime.now(timezone.utc).isoformat())
        
        pong_msg = {
            "type": "PONG",
            "msg_id": msg_id,
            "timestamp": timestamp,
            "ttl": 1
        }
        try:
            self.send_json(pong_msg)
            logger.debug("[%s] PONG enviado (msg_id=%s)", self.peer.peer_id, msg_id[:8] if len(msg_id) > 8 else msg_id)
        except Exception as exc:
            logger.debug("[%s] Falha ao enviar PONG: %s", self.peer.peer_id, exc)
    
    def _handle_pong(self, message: dict) -> None:
        """Processa PONG e calcula RTT baseado no msg_id."""
        try:
            msg_id = message.get("msg_id")
            
            # Olhar quando o PING foi enviado
            if msg_id and msg_id in self._pending_pings:
                sent_time = self._pending_pings.pop(msg_id)
                rtt = time.time() - sent_time
            else:
                # Fallback: tentar usar o timestamp da mensagem
                timestamp = message.get("timestamp")
                if timestamp is None:
                    logger.debug("[%s] PONG recebido sem msg_id conhecido", self.peer.peer_id)
                    return
                
                # Usar o timestamp como float ou ISO string
                if isinstance(timestamp, str):
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        sent_time = dt.timestamp()
                    except (ValueError, AttributeError):
                        logger.warning("[%s] PONG com timestamp inválido: %s", self.peer.peer_id, timestamp)
                        return
                else:
                    sent_time = timestamp
                
                rtt = time.time() - sent_time
            
            rtt_ms = rtt * 1000  # converter pra milisegungos
            
            # Sanity check: RTT should be positive and reasonable (< 60 seconds)
            if rtt < 0 or rtt > 60:
                logger.warning("[%s] RTT inválido ignorado: %.3fs", self.peer.peer_id, rtt)
                return

            self.rtt_samples.append(rtt)
            if len(self.rtt_samples) > 10:
                self.rtt_samples.pop(0)
            
            self.last_pong_time = time.time()
            
            # Utualizar PeerInfo average_rtt_ms com EMA (alpha=0.3)
            alpha = 0.3
            if self.peer.average_rtt_ms is None:
                self.peer.average_rtt_ms = rtt_ms
            else:
                self.peer.average_rtt_ms = alpha * rtt_ms + (1 - alpha) * self.peer.average_rtt_ms
            
            # Utualizar o last_seen_at
            self.peer.last_seen_at = datetime.now()
            
            logger.debug("[%s] PONG recebido - RTT: %.1fms (avg: %.1fms)", 
                        self.peer.peer_id, rtt_ms, self.peer.average_rtt_ms)

        except Exception as exc:
            logger.warning("[%s] Erro ao processar PONG: %s", self.peer.peer_id, exc)

    def get_metrics(self) -> dict:
        """Retorna métricas da conexão"""
        avg_rtt = sum(self.rtt_samples) / len(self.rtt_samples) if self.rtt_samples else 0

        return {
            "peer_id": self.peer.peer_id,
            "is_outbound": self.is_outbound,
            "avg_rtt": avg_rtt,
            "rtt_samples": len(self.rtt_samples),
            "last_pong": self.last_pong_time,
            "active": not self._stop_event.is_set()
        }

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
        # Timeout of 1 hour - connections should stay alive for long periods
        self.socket.settimeout(self.settings.extra.get("peer_read_timeout", 3600.0))
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

        if self._ping_thread and self._ping_thread.is_alive():
            self._ping_thread.join(timeout=1)

        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        finally:
            self.socket.close()
        if self._on_closed:
            self._on_closed(self)
