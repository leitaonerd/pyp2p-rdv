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


def find_default_config() -> Path | None:
    """Procura config.json no diretório do módulo ou diretório atual."""
    # Primeiro, tenta no diretório do módulo
    module_dir = Path(__file__).parent
    config_in_module = module_dir / "config.json"
    if config_in_module.exists():
        return config_in_module
    
    # Depois, tenta no diretório atual
    config_in_cwd = Path.cwd() / "config.json"
    if config_in_cwd.exists():
        return config_in_cwd
    
    return None


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

    # Auto-detect config file if not specified
    config_path = args.config if args.config else find_default_config()
    settings = ClientSettings.from_file(config_path)
    
    if config_path:
        print(f"Configuração carregada de: {config_path}")
    else:
        print("Usando configurações padrão (config.json não encontrado)")
    
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
