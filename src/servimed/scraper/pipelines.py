"""Pipeline: valida e normaliza cada item bruto da Servimed."""

from __future__ import annotations

import logging

from scrapy.exceptions import DropItem

from servimed.models import CAMPO_CODIGO, CAMPO_PRECO_PADRAO, ProdutoInvalido, normalizar_produto

logger = logging.getLogger(__name__)

STAT_VALIDOS = "servimed/itens_validos"
STAT_DESCARTADOS = "servimed/itens_descartados"


class ValidaProdutoPipeline:
    def __init__(self, campo_preco: str = CAMPO_PRECO_PADRAO, stats=None):
        self.campo_preco = campo_preco
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        campo = crawler.settings.get("SERVIMED_PRICE_FIELD", CAMPO_PRECO_PADRAO)
        return cls(campo_preco=campo, stats=crawler.stats)

    def _inc(self, chave: str) -> None:
        if self.stats:
            self.stats.inc_value(chave)

    def process_item(self, item, spider=None):
        try:
            produto = normalizar_produto(item, self.campo_preco)
        except ProdutoInvalido as exc:
            self._inc(STAT_DESCARTADOS)
            raise DropItem(f"item {item.get(CAMPO_CODIGO)!r} descartado: {exc}") from exc
        self._inc(STAT_VALIDOS)
        return produto.to_dict()