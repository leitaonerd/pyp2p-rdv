"""Configuration helpers for the PyP2P client.

Responsabilidades planejadas:
- Carregar arquivos ``config.json``/``.env`` e aplicar defaults seguros.
- Permitir overrides por variáveis de ambiente/CLI (ex.: host, namespace).
- Validar limites (payload, intervalo de discovery, tentativas de reconexão).
- Expor método ``peer_id`` com o formato ``name@namespace``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional


# Limites definidos na especificação
MAX_NAME_LENGTH = 64
MAX_NAMESPACE_LENGTH = 64
MIN_PORT = 1
MAX_PORT = 65535
MIN_TTL = 1
MAX_TTL = 86400  # 24 horas em segundos
MAX_PAYLOAD_BYTES = 32 * 1024  # 32KB


class ConfigValidationError(ValueError):
    """Erro de validação de configuração."""
    pass


def validate_name(name: str) -> str:
    """Valida o campo name (até 64 caracteres)."""
    if not isinstance(name, str):
        raise ConfigValidationError(f"name deve ser string, recebido: {type(name).__name__}")
    if len(name) == 0:
        raise ConfigValidationError("name não pode ser vazio")
    if len(name) > MAX_NAME_LENGTH:
        raise ConfigValidationError(f"name excede {MAX_NAME_LENGTH} caracteres: {len(name)}")
    return name


def validate_namespace(namespace: str) -> str:
    """Valida o campo namespace (até 64 caracteres)."""
    if not isinstance(namespace, str):
        raise ConfigValidationError(f"namespace deve ser string, recebido: {type(namespace).__name__}")
    if len(namespace) == 0:
        raise ConfigValidationError("namespace não pode ser vazio")
    if len(namespace) > MAX_NAMESPACE_LENGTH:
        raise ConfigValidationError(f"namespace excede {MAX_NAMESPACE_LENGTH} caracteres: {len(namespace)}")
    return namespace


def validate_port(port: int) -> int:
    """Valida o campo port (1-65535)."""
    if not isinstance(port, int):
        raise ConfigValidationError(f"port deve ser inteiro, recebido: {type(port).__name__}")
    if port < MIN_PORT or port > MAX_PORT:
        raise ConfigValidationError(f"port deve estar entre {MIN_PORT} e {MAX_PORT}, recebido: {port}")
    return port


def validate_ttl(ttl: int) -> int:
    """Valida o campo ttl (1-86400 segundos)."""
    if not isinstance(ttl, int):
        raise ConfigValidationError(f"ttl deve ser inteiro, recebido: {type(ttl).__name__}")
    if ttl < MIN_TTL or ttl > MAX_TTL:
        raise ConfigValidationError(f"ttl deve estar entre {MIN_TTL} e {MAX_TTL} segundos, recebido: {ttl}")
    return ttl


@dataclass(slots=True)
class ClientSettings:
    """Conjunto de parâmetros centrais do cliente.

    Os valores abaixo são defaults razoáveis para desenvolvimento local. A ideia
    é permitir overrides vindos de arquivo/CLI, mantendo validações simples por
    enquanto. Cada campo traz um comentário descrevendo a funcionalidade futura
    associada ao requisito da especificação.
    """

    name: str = "alice"
    namespace: str = "CIC"
    rendezvous_host: str = "pyp2p.mfcaetano.cc"
    rendezvous_port: int = 8080
    rendezvous_timeout: float = 10.0  # segundos
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

    def validate(self) -> None:
        """Valida todos os campos conforme especificação do protocolo.
        
        Raises:
            ConfigValidationError: Se algum campo estiver fora dos limites.
        """
        validate_name(self.name)
        validate_namespace(self.namespace)
        validate_port(self.listen_port)
        validate_port(self.rendezvous_port)
        validate_ttl(self.ttl_seconds)

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
        settings.validate()  # Valida após carregar
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
