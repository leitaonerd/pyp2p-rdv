"""Shared state models for the PyP2P client runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(slots=True)
class PeerInfo:
    """Representa um peer conhecido conforme mantido na ``PeerTable``."""

    peer_id: str
    address: str
    port: int
    namespace: str
    status: str = "UNKNOWN"  # TODO: usar Enum com CONNECTED/STALE/FAILED.
    last_seen_at: Optional[datetime] = None
    average_rtt_ms: Optional[float] = None
    reconnect_attempts: int = 0
    supports_ack: bool = True
    features: List[str] = field(default_factory=list)


@dataclass(slots=True)
class MessageRecord:
    """Metadados de uma mensagem enviada/recebida.

    TODOs relacionados:
    - Persistir as últimas N mensagens para `/conn` e `/rtt`.
    - Conferir tamanho e TTL antes de efetuar o envio.
    - Usar este registro para correlacionar ACKs e calcular latência.
    """

    msg_id: str
    src: str
    dst: str
    payload_preview: str
    timestamp: datetime
    acknowledged: bool = False
    ack_timestamp: Optional[datetime] = None
    error: Optional[str] = None


@dataclass(slots=True)
class ClientRuntimeState:
    """Estado compartilhado entre módulos (CLI, roteador, keep-alive)."""

    peers: Dict[str, PeerInfo] = field(default_factory=dict)
    outbound_history: List[MessageRecord] = field(default_factory=list)
    inbound_history: List[MessageRecord] = field(default_factory=list)
    connected_since: Optional[datetime] = None
    shutting_down: bool = False

    # TODO: considerar uso de ``asyncio.Lock``/``RLock`` conforme arquitetura final.
