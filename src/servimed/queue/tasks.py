from __future__ import annotations

import os
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from servimed.api.client import ApiTransientError, DesafioApiClient
from servimed.config import get_settings
from servimed.queue.celery_app import app

log = logging.getLogger(__name__)

RAIZ_PROJETO = Path(__file__).resolve().parents[3]  # onde está o scrapy.cfg


class ScrapeError(Exception):
    """Spider falhou ou não devolveu produtos (ex.: login recusado). Não vale retentar."""


def _rodar_spider(usuario: str, senha: str, saida: Path, timeout: int) -> None:
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "produtos",
        "-a", f"usuario={usuario}", "-a", f"senha={senha}",
        "-O", str(saida),
    ]
    log.info("iniciando spider produtos (usuario=%s)", usuario)  # nunca logar o cmd inteiro
    try:
        proc = subprocess.run(
            cmd, cwd=RAIZ_PROJETO, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise ScrapeError(f"spider excedeu {timeout}s") from exc
    if proc.returncode != 0:
        log.error("spider terminou com código %s: %s", proc.returncode, proc.stderr[-500:])
        raise ScrapeError(f"spider terminou com código {proc.returncode}")


def _ler_produtos(saida: Path) -> list[dict[str, Any]]:
    if not saida.exists() or saida.stat().st_size == 0:
        raise ScrapeError("spider não gerou produtos (login recusado ou falha na coleta)")
    produtos = json.loads(saida.read_text(encoding="utf-8"))
    if not produtos:
        raise ScrapeError("nenhum produto extraído")
    return produtos


@app.task(
    bind=True,
    name="servimed.scrape_produtos",
    autoretry_for=(ApiTransientError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=get_settings().task_soft_time_limit,
    time_limit=get_settings().task_time_limit,
)
def scrape_produtos(self, payload: dict[str, str]) -> dict[str, int]:
    cfg = get_settings()
    usuario, senha = payload["usuario"], payload["senha"]
    log.info("task %s iniciada (usuario=%s)", self.request.id, usuario)

    cfg.tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cfg.tmp_dir) as tmp:
        saida = Path(tmp) / "produtos.json"
        _rodar_spider(usuario, senha, saida, timeout=max(60, cfg.task_soft_time_limit - 30))
        produtos = _ler_produtos(saida)

    api_user, api_pass = cfg.require_desafio_credentials()
    cliente = DesafioApiClient(
        cfg.desafio_api_base_url,
        api_user,
        api_pass,
        timeout=int(cfg.desafio_api_timeout),
        batch_size=cfg.desafio_api_batch_size,
    )
    enviados = cliente.enviar_produtos(produtos)
    log.info("task %s concluída: %s extraídos, %s enviados", self.request.id, len(produtos), enviados)
    return {"extraidos": len(produtos), "enviados": enviados}

def _rodar_spider(usuario: str, senha: str, saida: Path, timeout: int) -> None:
    env = {**os.environ, "SCRAPY_SETTINGS_MODULE": "servimed.scraper.settings"}
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "produtos",
        "-a", f"usuario={usuario}", "-a", f"senha={senha}",
        "-O", str(saida),
    ]
    log.info("iniciando spider produtos (usuario=%s)", usuario)
    try:
        proc = subprocess.run(
            cmd, cwd=RAIZ_PROJETO, env=env, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise ScrapeError(f"spider excedeu {timeout}s") from exc
    if proc.returncode != 0:
        log.error("spider terminou com código %s: %s", proc.returncode, proc.stderr[-500:])
        raise ScrapeError(f"spider terminou com código {proc.returncode}")