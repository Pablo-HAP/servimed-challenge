"""
Regra do projeto: nunca registrar senha, token ou cookie. Registre apenas o
usuário, o id da tarefa e contagens.
"""

from __future__ import annotations

import logging
import sys

from servimed.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Bibliotecas barulhentas em nível INFO/DEBUG.
_NOISY_LOGGERS = ("urllib3", "asyncio")


def setup_logging(level: str | None = None) -> None:
    """Configura o logger raiz. Chame uma vez por processo."""
    resolved = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=resolved,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stdout,
        force=True,  # substitui handlers criados antes por outras bibliotecas
    )
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)