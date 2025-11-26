"""Entry-point helper for running the PyP2P client."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from .config import ClientSettings
from .p2p_client import P2PClient


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PyP2P client")
    parser.add_argument("--config", type=Path, help="Caminho para arquivo de configuração", default=None)
    parser.add_argument("--log-level", help="Override de nível de log", default=None)
    return parser


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    settings = ClientSettings.from_file(args.config)
    if args.log_level:
        settings.log_level = args.log_level.upper()

    configure_logging(settings.log_level)
    client = P2PClient(settings)

    # Event to signal shutdown
    shutdown_event = threading.Event()

    def signal_handler(sig, frame):
        print("\nRecebido sinal de interrupção. Encerrando...")
        shutdown_event.set()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        client.start()
        print(f"\nCliente P2P iniciado como {settings.peer_id}")
        print("Digite /help para ver os comandos disponíveis.\n")
        
        # Wait until shutdown is signaled or CLI thread ends
        while not shutdown_event.is_set() and client._running:
            # Check if CLI thread is still alive
            if client.cli._thread and not client.cli._thread.is_alive():
                break
            shutdown_event.wait(timeout=0.5)
            
    except KeyboardInterrupt:
        pass
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
