"""Networking helpers for talking to the rendezvous server."""
from __future__ import annotations

import json
import logging
import socket
from contextlib import closing
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import ClientSettings
from .state import PeerInfo


logger = logging.getLogger(__name__)


class RendezvousError(RuntimeError):
    """Erro genérico envolvendo interação com o rendezvous."""


class RendezvousClient:
    """Encapsula REGISTER/DISCOVER/UNREGISTER."""

    def __init__(self, settings: ClientSettings) -> None:
        self.settings = settings
        self._registered = False

    def _send_request(self, payload: Dict[str, object]) -> Dict[str, object]:
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            with closing(
                socket.create_connection(
                    (self.settings.rendezvous_host, self.settings.rendezvous_port),
                    timeout=self.settings.rendezvous_timeout,
                )
            ) as sock:
                sock.sendall(line.encode("utf-8"))
                response = self._recv_line(sock)
        except OSError as exc:
            raise RendezvousError(f"Erro de rede com rendezvous: {exc}") from exc

        try:
            data = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RendezvousError(f"Resposta inválida do rendezvous: {response}") from exc

        return data

    @staticmethod
    def _recv_line(sock: socket.socket) -> str:
        chunks: List[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        data = b"".join(chunks)
        if b"\n" in data:
            data = data.split(b"\n", 1)[0]
        return data.decode("utf-8", errors="replace")

    def register(self, port: Optional[int] = None, ttl: Optional[int] = None) -> Dict[str, object]:
        payload = {
            "type": "REGISTER",
            "namespace": self.settings.namespace,
            "name": self.settings.name,
            "port": port or self.settings.listen_port,
            "ttl": ttl or self.settings.ttl_seconds,
        }
        data = self._send_request(payload)
        if data.get("status") != "OK":
            raise RendezvousError(f"REGISTER falhou: {data}")
        self._registered = True
        logger.info(
            "Registrado no rendezvous como %s:%s",
            data.get("ip"),
            data.get("port"),
        )
        return data

    def discover_peers(self, namespace: Optional[str] = None) -> List[PeerInfo]:
        payload: Dict[str, object] = {"type": "DISCOVER"}
        if namespace:
            payload["namespace"] = namespace
        data = self._send_request(payload)
        if data.get("status") != "OK":
            raise RendezvousError(f"DISCOVER falhou: {data}")

        peers_payload = data.get("peers", [])
        if not isinstance(peers_payload, list):
            logger.warning("Lista de peers inválida recebida: %s", peers_payload)
            return []
        results: List[PeerInfo] = []
        now = datetime.now(timezone.utc)
        for peer in peers_payload:
            try:
                peer_info = PeerInfo(
                    peer_id=f"{peer['name']}@{peer['namespace']}",
                    address=peer["ip"],
                    port=int(peer["port"]),
                    namespace=peer["namespace"],
                    status="DISCOVERED",
                    last_seen_at=now,
                    features=[],
                )
                results.append(peer_info)
            except KeyError as exc:
                logger.warning("Peer inválido recebido do rendezvous: %s", peer)
                continue

        return results

    def unregister(self, port: Optional[int] = None) -> None:
        if not self._registered:
            return
        payload = {
            "type": "UNREGISTER",
            "namespace": self.settings.namespace,
            "name": self.settings.name,
            "port": port or self.settings.listen_port,
        }
        data = self._send_request(payload)
        if data.get("status") != "OK":
            raise RendezvousError(f"UNREGISTER falhou: {data}")
        self._registered = False
        logger.info("Peer removido do rendezvous")

    def is_registered(self) -> bool:
        return self._registered
