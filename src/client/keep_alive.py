"""Keep-alive utilities for PING/PONG handling."""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from .config import ClientSettings
from .peer_table import PeerTable


class KeepAliveManager:
    """Dispara PINGs periódicos e processa PONGs para calcular RTT."""

    def __init__(self, settings: ClientSettings, peer_table: PeerTable) -> None:
        self.settings = settings
        self.peer_table = peer_table
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Inicia a thread de keep-alive.

        TODO:
        - Usar ``threading.Timer`` ou ``asyncio`` para enviar PING a cada intervalo.
        - Registrar timestamp por peer e atualizar RTT ao receber PONG.
        - Emitir logs/alertas quando peer não responder dentro do SLA.
        """

        if self._thread and self._thread.is_alive():
            return

        def _loop() -> None:
            while not self._stop_event.is_set():
                # Placeholder: apenas dorme; substituir por envio real de PING.
                self._stop_event.wait(self.settings.ping_interval)

        self._stop_event.clear()
        self._thread = threading.Thread(target=_loop, name="keep-alive", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2)

    def handle_pong(self, peer_id: str, sent_at: datetime) -> None:
        """Atualiza o RTT no ``PeerInfo`` correspondente."""

        # TODO: localizar peer e atualizar ``average_rtt_ms`` usando EMA.
        _ = (peer_id, sent_at)
