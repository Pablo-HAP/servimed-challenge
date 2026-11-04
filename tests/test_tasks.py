# tests/test_tasks.py
import json

import pytest

from servimed.queue import tasks


def test_task_envia_produtos(monkeypatch):
    produtos = [{"gtin": "1", "codigo": "A", "descricao": "x", "preco_fabrica": 1.0, "estoque": 1}]

    def spider_falso(usuario, senha, saida, timeout):
        saida.write_text(json.dumps(produtos), encoding="utf-8")

    class ClienteFalso:
        def __init__(self, *a, **kw): ...
        def enviar_produtos(self, p):
            return len(p)

    monkeypatch.setattr(tasks, "_rodar_spider", spider_falso)
    monkeypatch.setattr(tasks, "DesafioApiClient", ClienteFalso)
    monkeypatch.setenv("DESAFIO_API_USER", "u")
    monkeypatch.setenv("DESAFIO_API_PASSWORD", "p")
    tasks.get_settings.cache_clear()

    assert tasks.scrape_produtos.run({"usuario": "a", "senha": "b"}) == {"extraidos": 1, "enviados": 1}


def test_sem_produtos_levanta_scrape_error(monkeypatch):
    monkeypatch.setattr(tasks, "_rodar_spider", lambda *a, **kw: None)  # não gera arquivo
    with pytest.raises(tasks.ScrapeError):
        tasks.scrape_produtos.run({"usuario": "a", "senha": "b"})