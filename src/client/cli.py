"""Command-line interface loop placeholder."""
from __future__ import annotations

import threading
from typing import Callable, Optional

from .message_router import MessageRouter
from .peer_table import PeerTable


class CommandLineInterface:
    """Responsável pelos comandos `/peers`, `/msg`, `/pub`, etc."""

    def __init__(
        self,
        router: MessageRouter,
        peer_table: PeerTable,
        prompt: str = "pyp2p> ",
    ) -> None:
        self.router = router
        self.peer_table = peer_table
        self.prompt = prompt
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._output_callback: Optional[Callable[[str], None]] = None

    def attach_output(self, callback: Callable[[str], None]) -> None:
        """Permite redirecionar mensagens da CLI para testes/UI."""

        self._output_callback = callback

    def start(self) -> None:
        """Inicia o loop interativo em uma thread dedicada.

        TODOs principais:
        - Implementar parser real (provavelmente `cmd.Cmd` ou `prompt_toolkit`).
        - Garantir que o loop não bloqueie o recebimento de mensagens.
        - Exibir ajuda contextual (`/help`).
        - Integrar níveis de log (comando `/log`).
        """

        if self._thread and self._thread.is_alive():
            return

        def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    user_input = input(self.prompt)
                except (EOFError, KeyboardInterrupt):
                    break
                self._handle_command(user_input.strip())

        self._stop_event.clear()
        self._thread = threading.Thread(target=_loop, name="cli", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2)
        self._thread = None

    def _handle_command(self, raw_command: str) -> None:
        if not raw_command:
            return
        # TODO: parsear comandos reais. Por enquanto, apenas imprime.
        self._emit(f"[CLI] Comando recebido (stub): {raw_command}")

    def _emit(self, message: str) -> None:
        if self._output_callback:
            self._output_callback(message)
        else:
            print(message)
