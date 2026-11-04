"""Configuração central do projeto.

Lê variáveis de ambiente (e o arquivo .env, se existir) e expõe um objeto
imutável `Settings`. Nenhum outro módulo deve chamar `os.getenv` diretamente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, TypeVar

from dotenv import load_dotenv

# Variáveis já definidas no ambiente têm prioridade sobre o .env (útil em
# Docker/CI). Rode os comandos a partir da raiz do repositório.
load_dotenv()

T = TypeVar("T", int, float)

_TRUE = {"1", "true", "yes", "sim", "on"}
_FALSE = {"0", "false", "no", "nao", "não", "off"}


class ConfigError(RuntimeError):
    """Variável de ambiente ausente ou com valor inválido."""


def _text(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _number(name: str, default: T, cast: Callable[[str], T]) -> T:
    raw = _text(name)
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} inválida: {raw!r} (esperado {cast.__name__})") from exc


def _flag(name: str, default: bool) -> bool:
    raw = _text(name).lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"{name} inválida: {raw!r} (esperado true/false)")


@dataclass(frozen=True)
class Settings:
    """Configuração imutável. Senhas ficam fora do repr para não vazar em logs."""

    # --- Servimed ---
    servimed_user: str = field(repr=False)
    servimed_password: str = field(repr=False)
    servimed_api_base_url: str
    servimed_site_origin: str
    servimed_site_version: str
    servimed_price_field: str

    # --- Scrapy ---
    scrapy_download_delay: float
    scrapy_concurrent_requests: int
    scrapy_log_level: str
    scrapy_user_agent: str
    scrapy_robotstxt_obey: bool

    # --- API do desafio ---
    desafio_api_base_url: str
    desafio_api_user: str = field(repr=False)
    desafio_api_password: str = field(repr=False)
    desafio_api_timeout: float
    desafio_api_batch_size: int

    # --- Fila ---
    redis_url: str
    task_soft_time_limit: int
    task_time_limit: int

    # --- Geral ---
    log_level: str
    tmp_dir: Path

    def require_servimed_credentials(self) -> tuple[str, str]:
        """Credenciais padrão para execução local (fora da fila)."""
        if not self.servimed_user or not self.servimed_password:
            raise ConfigError("Defina SERVIMED_USER e SERVIMED_PASSWORD no .env")
        return self.servimed_user, self.servimed_password

    def require_desafio_credentials(self) -> tuple[str, str]:
        """Credenciais do usuário criado em /oauth/signup."""
        if not self.desafio_api_user or not self.desafio_api_password:
            raise ConfigError("Defina DESAFIO_API_USER e DESAFIO_API_PASSWORD no .env")
        return self.desafio_api_user, self.desafio_api_password


def _load() -> Settings:
    settings = Settings(
        servimed_user=_text("SERVIMED_USER"),
        servimed_password=_text("SERVIMED_PASSWORD"),
        servimed_api_base_url=_text("SERVIMED_API_BASE_URL", "https://peapi.servimed.com.br").rstrip("/"),
        servimed_site_origin=_text("SERVIMED_SITE_ORIGIN", "https://pedidoeletronico.servimed.com.br").rstrip("/"),
        servimed_site_version=_text("SERVIMED_SITE_VERSION", "4.0.29"),
        servimed_price_field=_text("SERVIMED_PRICE_FIELD", "valorBase"),
        scrapy_download_delay=_number("SCRAPY_DOWNLOAD_DELAY", 0.25, float),
        scrapy_concurrent_requests=_number("SCRAPY_CONCURRENT_REQUESTS", 4, int),
        scrapy_log_level=_text("SCRAPY_LOG_LEVEL", "INFO").upper(),
        scrapy_user_agent=_text("SCRAPY_USER_AGENT"),
        scrapy_robotstxt_obey=_flag("SCRAPY_ROBOTSTXT_OBEY", True),
        desafio_api_base_url=_text("DESAFIO_API_BASE_URL", "https://desafio.cotefacil.net").rstrip("/"),
        desafio_api_user=_text("DESAFIO_API_USER"),
        desafio_api_password=_text("DESAFIO_API_PASSWORD"),
        desafio_api_timeout=_number("DESAFIO_API_TIMEOUT", 10.0, float),
        desafio_api_batch_size=_number("DESAFIO_API_BATCH_SIZE", 500, int),
        redis_url=_text("REDIS_URL", "redis://localhost:6379/0"),
        task_soft_time_limit=_number("TASK_SOFT_TIME_LIMIT", 1500, int),
        task_time_limit=_number("TASK_TIME_LIMIT", 1800, int),
        log_level=_text("LOG_LEVEL", "INFO").upper(),
        tmp_dir=Path(_text("TMP_DIR", "tmp")),
    )
    _validate(settings)
    return settings


def _validate(s: Settings) -> None:
    if s.desafio_api_batch_size < 1:
        raise ConfigError("DESAFIO_API_BATCH_SIZE deve ser >= 1")
    if s.desafio_api_timeout <= 0:
        raise ConfigError("DESAFIO_API_TIMEOUT deve ser > 0")
    if s.scrapy_concurrent_requests < 1:
        raise ConfigError("SCRAPY_CONCURRENT_REQUESTS deve ser >= 1")
    if s.task_soft_time_limit >= s.task_time_limit:
        raise ConfigError("TASK_SOFT_TIME_LIMIT deve ser menor que TASK_TIME_LIMIT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna as configurações (carregadas uma única vez por processo)."""
    return _load()