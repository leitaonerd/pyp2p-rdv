"""Configuration helpers for the PyP2P client.

Responsabilidades planejadas:
- Carregar arquivos ``config.json``/``.env`` e aplicar defaults seguros.
- Permitir overrides por variáveis de ambiente/CLI (ex.: host, namespace).
- Validar limites (payload, intervalo de discovery, tentativas de reconexão).
- Expor método ``peer_id`` com o formato ``name@namespace``.
- No futuro, suportar múltiplos perfis (prod, staging, mock rendezvous).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(slots=True)
class ClientSettings:
    """Conjunto de parâmetros centrais do cliente.

    Os valores abaixo são defaults razoáveis para desenvolvimento local. A ideia
    é permitir overrides vindos de arquivo/CLI, mantendo validações simples por
    enquanto. Cada campo traz um comentário descrevendo a funcionalidade futura
    associada ao requisito da especificação.
    """

    name: str = "rafael"  # TODO: permitir definir via CLI (/set name) ou config.
    namespace: str = "CIC"  # TODO: validar com regex; aceitar `#namespace` no CLI.
    rendezvous_host: str = "pyp2p.mfcaetano.cc"
    rendezvous_port: int = 8080
    rendezvous_timeout: float = 5.0  # segundos
    listen_host: str = "0.0.0.0"
    listen_port: int = 6000
    ttl_seconds: int = 7200
    discovery_interval: float = 15.0  # segundos; configurável (ver seção 2.3 do plano).
    ping_interval: float = 30.0  # segundos; usado pelo keep-alive.
    reconnect_backoff_base: float = 2.0
    max_reconnect_attempts: int = 5
    max_payload_bytes: int = 32 * 1024
    log_level: str = "INFO"
    save_logs_to_file: bool = False
    log_file_path: Optional[Path] = None
    config_file: Optional[Path] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def peer_id(self) -> str:
        """Retorna o identificador ``name@namespace`` exigido pelo protocolo."""

        return f"{self.name}@{self.namespace}"

    @classmethod
    def from_file(cls, path: Optional[Path]) -> "ClientSettings":
        """Carrega configurações de um arquivo JSON, se existir."""

        if path is None or not path.exists():
            return cls(config_file=path)

        with path.open("r", encoding="utf-8") as fp:
            raw_data = json.load(fp)

        known_fields = {f.name for f in fields(cls)}
        init_kwargs: Dict[str, Any] = {
            key: value for key, value in raw_data.items() if key in known_fields
        }
        extra = {key: value for key, value in raw_data.items() if key not in known_fields}
        settings = cls(**init_kwargs, config_file=path)
        settings.extra.update(extra)
        return settings

    def to_dict(self) -> Dict[str, Any]:
        """Exporta a configuração atual (útil para logs e debug)."""

        return {
            "name": self.name,
            "namespace": self.namespace,
            "peer_id": self.peer_id,
            "rendezvous_host": self.rendezvous_host,
            "rendezvous_port": self.rendezvous_port,
            "rendezvous_timeout": self.rendezvous_timeout,
            "listen_host": self.listen_host,
            "listen_port": self.listen_port,
            "ttl_seconds": self.ttl_seconds,
            "discovery_interval": self.discovery_interval,
            "ping_interval": self.ping_interval,
            "max_payload_bytes": self.max_payload_bytes,
            "log_level": self.log_level,
            "save_logs_to_file": self.save_logs_to_file,
            "log_file_path": str(self.log_file_path) if self.log_file_path else None,
            "extra": self.extra,
        }
