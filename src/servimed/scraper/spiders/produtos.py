"""Spider: login na API da Servimed e extração do catálogo.

Fluxo: login (JSON) -> lê codigoUsuario/codigoExterno e o token do cookie ->
busca a página 1 -> lê totalRegistros -> agenda as demais páginas.
Falhas são registradas em stats (lidas pelo run_spider para o código de saída).
"""

from __future__ import annotations

import base64
import json
import math
from typing import Any

import scrapy
from scrapy.exceptions import CloseSpider
from scrapy.http import JsonRequest

from servimed.config import get_settings
from servimed.scraper.auth import SessaoInvalida, extrair_access_token
from servimed.scraper.payloads import build_search_payload

MENSAGEM_CREDENCIAL_INVALIDA = "usuário ou senha inválidos"

STAT_LOGIN_FALHOU = "servimed/login_falhou"  # credencial recusada
STAT_LOGIN_ERRO = "servimed/login_erro"  # qualquer outro problema no login
STAT_PAGINAS_COM_ERRO = "servimed/paginas_com_erro"
STAT_TOTAL_REGISTROS = "servimed/total_registros"
STAT_ITENS_RECEBIDOS = "servimed/itens_recebidos"


def _uuid_do_jwt(jwt: str) -> str:
    """Extrai o UUID (campo `token`) do payload de um JWT, sem validar a assinatura."""
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["token"]


def _normalizar_token(token: str) -> str:
    """O header `accesstoken` da Servimed leva o UUID, não o JWT inteiro.

    Se `token` tem cara de JWT (três partes separadas por ponto), converte para o UUID;
    se já for o UUID, devolve como está.
    """
    if token.count(".") == 2:
        return _uuid_do_jwt(token)
    return token


class ProdutosSpider(scrapy.Spider):
    name = "produtos"

    def __init__(self, usuario: str | None = None, senha: str | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        if not usuario or not senha:
            raise ValueError("Informe usuario e senha (-a usuario=... -a senha=...)")
        self._usuario = usuario
        self._senha = senha
        cfg = get_settings()
        self._api = cfg.servimed_api_base_url
        self._origin = cfg.servimed_site_origin
        self._site_version = cfg.servimed_site_version
        self._sessao: dict[str, Any] = {}

    # ---------- stats (tolerante a spider sem crawler, como nos testes) ----------
    def _stats(self):
        crawler = getattr(self, "crawler", None)
        return crawler.stats if crawler else None

    def _inc(self, chave: str, valor: int = 1) -> None:
        stats = self._stats()
        if stats:
            stats.inc_value(chave, valor)

    def _set(self, chave: str, valor: Any) -> None:
        stats = self._stats()
        if stats:
            stats.set_value(chave, valor)

    # ---------- login ----------
    def _headers_base(self) -> dict[str, str]:
        return {
            "Origin": self._origin,
            "Referer": f"{self._origin}/",
            "Accept": "application/json, text/plain, */*",
        }

    async def start(self):  # Scrapy >= 2.13
        yield JsonRequest(
            url=f"{self._api}/api/usuario/login",
            data={"usuario": self._usuario, "senha": self._senha},
            headers={**self._headers_base(), "loggedUser": "0"},
            # A Servimed responde 500 para credencial inválida: o callback precisa
            # ver essa resposta e o retry não pode repetir o login.
            meta={"handle_httpstatus_all": True, "dont_retry": True},
            callback=self.apos_login,
            errback=self.erro_login,
            dont_filter=True,
        )

    @staticmethod
    def _texto_resposta(response) -> str:
        try:
            return json.dumps(response.json(), ensure_ascii=False).lower()
        except ValueError:
            return response.text.lower()

    def _falha_login(self, motivo: str):
        self._set(STAT_LOGIN_ERRO, True)
        self.logger.error("Falha no login: %s", motivo)
        raise CloseSpider("erro_login")

    def apos_login(self, response):
        if response.status == 500 and MENSAGEM_CREDENCIAL_INVALIDA in self._texto_resposta(response):
            self._set(STAT_LOGIN_FALHOU, True)
            self.logger.error("Credenciais recusadas pela Servimed (usuário=%s)", self._usuario)
            raise CloseSpider("credenciais_invalidas")
        if response.status != 200:
            self._falha_login(f"status inesperado {response.status}")
        try:
            usuario = response.json()["usuario"]
            self._sessao = {
                "codigo_usuario": usuario["codigoUsuario"],
                "codigo_externo": usuario["codigoExterno"],
                "users": usuario.get("users"),
                # O header `accesstoken` leva o UUID de dentro do JWT do cookie.
                "access_token": _normalizar_token(
                    extrair_access_token(response.headers.getlist("Set-Cookie"))
                ),
            }
        except (ValueError, KeyError, IndexError, TypeError, SessaoInvalida) as exc:
            self._falha_login(f"resposta de login inesperada ({type(exc).__name__}: {exc})")
        self.logger.info("Login ok (usuário=%s)", self._usuario)
        return self._pagina_request(1)

    def erro_login(self, failure):
        self._falha_login(f"erro de rede/HTTP ({failure.value!r})")

    # ---------- listagem ----------
    def _pagina_request(self, pagina: int) -> JsonRequest:
        s = self._sessao
        return JsonRequest(
            url=f"{self._api}/api/carrinho/oculto?siteVersion={self._site_version}",
            data=build_search_payload(pagina, s["codigo_usuario"], s["codigo_externo"], s["users"]),
            headers={
                **self._headers_base(),
                "loggedUser": str(s["codigo_usuario"]),
                "accesstoken": s["access_token"],
            },
            callback=self.parse_pagina,
            errback=self.erro_pagina,
            cb_kwargs={"pagina": pagina},
        )

    def parse_pagina(self, response, pagina: int):
        try:
            dados = response.json()
            lista = dados["lista"]
            total = int(dados["totalRegistros"])
        except (ValueError, KeyError, TypeError) as exc:
            self._inc(STAT_PAGINAS_COM_ERRO)
            self.logger.error("Página %s com resposta inesperada: %s: %s", pagina, type(exc).__name__, exc)
            return

        self._inc(STAT_ITENS_RECEBIDOS, len(lista))

        if pagina == 1:
            self._set(STAT_TOTAL_REGISTROS, total)
            por_pagina = len(lista)  # tamanho REAL (o servidor ignora o pedido de 1000)
            if por_pagina and total > por_pagina:
                total_paginas = math.ceil(total / por_pagina)
                self.logger.info(
                    "Total de %s produtos, %s por página: %s páginas", total, por_pagina, total_paginas
                )
                for proxima in range(2, total_paginas + 1):
                    yield self._pagina_request(proxima)
        elif not lista:
            self.logger.warning("Página %s veio vazia", pagina)

        for item in lista:
            if isinstance(item, dict):
                yield item

    def erro_pagina(self, failure):
        pagina = failure.request.cb_kwargs.get("pagina")
        self._inc(STAT_PAGINAS_COM_ERRO)
        self.logger.error("Falha ao obter a página %s: %r", pagina, failure.value)

    # ---------- encerramento ----------
    def closed(self, reason: str):
        stats = self._stats()
        if not stats:
            return
        total = stats.get_value(STAT_TOTAL_REGISTROS)
        validos = stats.get_value("servimed/itens_validos", 0)
        descartados = stats.get_value("servimed/itens_descartados", 0)
        self.logger.info(
            "Encerrado (%s): total anunciado=%s, válidos=%s, descartados=%s",
            reason, total, validos, descartados,
        )
        if total is not None and validos + descartados != total:
            self.logger.warning(
                "A soma de válidos e descartados (%s) difere do total anunciado (%s)",
                validos + descartados, total,
            )