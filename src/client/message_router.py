"""Routing helpers for SEND/PUB/BYE."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, Optional
from uuid import uuid4

from .peer_table import PeerTable
from .state import ClientRuntimeState, MessageRecord


class MessageRouter:
    """Entrega mensagens para os peers conectados.

    Próximos passos:
    - Manter fila de saída para não bloquear a thread da CLI.
    - Gerenciar pedidos de ACK e timeouts (5s) com alertas nos logs.
    - Tratar PUB para ``*`` e ``#namespace`` evitando duplicidades.
    - Emitir eventos para o CLI (mensagens recebidas e status de entrega).
    """

    def __init__(self, peer_table: PeerTable, state: ClientRuntimeState) -> None:
        self.peer_table = peer_table
        self.state = state

    def send(self, dst_peer_id: str, payload: str, require_ack: bool = True) -> MessageRecord:
        msg_id = str(uuid4())
        record = MessageRecord(
            msg_id=msg_id,
            src="",  # TODO: preencher com peer_id local.
            dst=dst_peer_id,
            payload_preview=payload[:40],
            timestamp=datetime.utcnow(),
        )
        # TODO: localizar PeerConnection, enviar mensagem e monitorar ACK.
        self.state.outbound_history.append(record)
        return record

    def publish(self, namespace: str, payload: str) -> Dict[str, MessageRecord]:
        """Envia PUB para um namespace ou broadcast global."""

        results: Dict[str, MessageRecord] = {}
        peers = self.peer_table.all()
        filtered: Iterable = (
            peer for peer in peers if namespace in {"*", peer.namespace, f"#{peer.namespace}"}
        )
        for peer in filtered:
            results[peer.peer_id] = self.send(peer.peer_id, payload, require_ack=False)
        return results

    def handle_incoming(self, message: dict) -> None:
        """Integra com CLI/estado quando chegar mensagem recebida."""

        # TODO: validar assinatura JSON, TTL e, se for ACK, atualizar ``outbound_history``.
        _ = message
