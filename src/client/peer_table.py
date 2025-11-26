"""Thread-safe in-memory registry of peers known to the client."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, Iterable, Optional, Set

from .state import PeerInfo


class PeerTable:
    """Mantém o estado dos peers com políticas de limite e reconexão.

    Funcionalidades planejadas (ver Seção 3 do plano):
    - Aplicar limites de conexões inbound/outbound e desalocar peers ``STALE``.
    - Atualizar RTT médio sempre que um PONG/ACK é recebido.
    - Registrar tentativas de reconexão para `max_reconnect_attempts`.
    - Fornecer snapshots para comandos `/peers`, `/conn` e `/rtt`.
    """

    def __init__(self, max_outbound: int = 16, max_inbound: int = 16) -> None:
        self._peers: Dict[str, PeerInfo] = {}
        self._lock = RLock()
        self.max_outbound = max_outbound
        self.max_inbound = max_inbound

    def upsert_peer(self, peer: PeerInfo) -> None:
        """Adiciona ou atualiza um peer."""
        with self._lock:
            self._peers[peer.peer_id] = peer

    def get(self, peer_id: str) -> Optional[PeerInfo]:
        with self._lock:
            return self._peers.get(peer_id)

    def mark_stale(self, peer_id: str) -> None:
        with self._lock:
            entry = self._peers.get(peer_id)
            if entry:
                entry.status = "STALE"

    def all(self) -> Iterable[PeerInfo]:
        with self._lock:
            return list(self._peers.values())

    def remove(self, peer_id: str) -> None:
        with self._lock:
            self._peers.pop(peer_id, None)

    def stats(self) -> Dict[str, int]:
        """Retorna contadores básicos usados pelos comandos `/conn` e `/rtt`."""

        with self._lock:
            total = len(self._peers)
            connected = sum(1 for peer in self._peers.values() if peer.status == "CONNECTED")
            stale = sum(1 for peer in self._peers.values() if peer.status == "STALE")
        return {"total": total, "connected": connected, "stale": stale}

    def mark_missing_as_stale(self, seen_peer_ids: Set[str], stale_after: float) -> None:
        """Marca peers não vistos recentemente como STALE."""

        threshold = timedelta(seconds=stale_after)
        now = datetime.now(timezone.utc)
        with self._lock:
            for peer in self._peers.values():
                if peer.peer_id in seen_peer_ids:
                    continue
                if peer.last_seen_at and now - peer.last_seen_at > threshold:
                    peer.status = "STALE"
