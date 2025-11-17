"""Abstrações para conexões TCP com outros peers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .state import PeerInfo


@dataclass
class PeerConnection:
    """Representa uma conexão (inbound ou outbound) com outro peer.

    Roadmap:
    - Abrir sockets TCP, aplicar timeout e TLS (se necessário).
    - Realizar handshake HELLO/HELLO_OK, validando ``features``.
    - Expor métodos ``send``/``receive`` e acionar ``MessageRouter``.
    - Integrar com mecanismo de reconexão/backoff ao detectar falhas.
    """

    peer: PeerInfo
    reader: Optional[object] = None  # TODO: substituir por stream/socket real.
    writer: Optional[object] = None
    is_outbound: bool = False

    def connect(self) -> None:
        """Estabelece a conexão com o peer.

        TODO: abrir socket, enviar HELLO e aguardar HELLO_OK.
        """

    def close(self) -> None:
        """Garante BYE/BYE_OK e libera recursos."""

    def send_json(self, message: dict) -> None:
        """Serializa o dicionário em JSON, respeitando o limite de 32 KiB."""

        # TODO: validar tamanho do payload e enviar via socket real.
        _ = message
