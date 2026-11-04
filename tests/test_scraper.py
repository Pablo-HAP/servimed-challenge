import base64
import json

import pytest
from scrapy import Request
from scrapy.exceptions import CloseSpider
from scrapy.http import Headers, TextResponse

from servimed.scraper.auth import SessaoInvalida, extrair_access_token
from servimed.scraper.spiders.produtos import ProdutosSpider

UUID = "11111111-2222-3333-4444-555555555555"


def fazer_jwt(payload: dict) -> str:
    def b64(dado: bytes) -> str:
        return base64.urlsafe_b64encode(dado).rstrip(b"=").decode()

    return ".".join([b64(b'{"alg":"HS256"}'), b64(json.dumps(payload).encode()), "assinatura"])


def set_cookies(*pares):
    return [f"{nome}={valor}; Domain=.servimed.com.br; Path=/".encode() for nome, valor in pares]


def resposta(corpo, status=200, cb_kwargs=None, headers=None):
    url = "https://peapi.servimed.com.br/x"
    return TextResponse(
        url=url,
        status=status,
        body=json.dumps(corpo, ensure_ascii=False).encode(),
        encoding="utf-8",
        headers=headers,
        request=Request(url, cb_kwargs=cb_kwargs or {}),
    )


# ---------------- auth ----------------
def test_extrai_uuid_do_cookie_accesstoken():
    headers = set_cookies(("accesstoken", fazer_jwt({"token": UUID})), ("sessiontoken", "x.y.z"))
    assert extrair_access_token(headers) == UUID


def test_cookie_repetido_vale_o_ultimo():
    headers = set_cookies(
        ("accesstoken", fazer_jwt({"token": "antigo"})),
        ("accesstoken", fazer_jwt({"token": UUID})),
    )
    assert extrair_access_token(headers) == UUID


@pytest.mark.parametrize(
    "headers",
    [
        [],
        set_cookies(("sessiontoken", "a.b.c")),
        set_cookies(("accesstoken", "nao-e-jwt")),
        set_cookies(("accesstoken", fazer_jwt({"outro": 1}))),
    ],
)
def test_sessao_invalida(headers):
    with pytest.raises(SessaoInvalida):
        extrair_access_token(headers)


# ---------------- spider ----------------
@pytest.fixture
def spider():
    return ProdutosSpider(usuario="u@x.com", senha="segredo")


def test_spider_exige_credenciais():
    with pytest.raises(ValueError):
        ProdutosSpider(usuario="u@x.com")


def test_login_recusado_fecha_o_spider(spider):
    r = resposta({"message": "Usuário ou senha inválidos"}, status=500)
    with pytest.raises(CloseSpider) as exc:
        spider.apos_login(r)
    assert exc.value.reason == "credenciais_invalidas"


def test_login_com_unicode_escapado_tambem_e_reconhecido(spider):
    corpo = b'{"message": "Usu\\u00e1rio ou senha inv\\u00e1lidos"}'
    r = TextResponse("https://peapi.servimed.com.br/x", status=500, body=corpo, encoding="utf-8")
    with pytest.raises(CloseSpider) as exc:
        spider.apos_login(r)
    assert exc.value.reason == "credenciais_invalidas"


def test_login_500_com_outra_mensagem_e_erro_generico(spider):
    with pytest.raises(CloseSpider) as exc:
        spider.apos_login(resposta({"message": "falha interna"}, status=500))
    assert exc.value.reason == "erro_login"


def test_login_ok_pede_a_primeira_pagina(spider):
    corpo = {"usuario": {"codigoUsuario": 1, "codigoExterno": 2, "users": [2]}}
    headers = Headers({"Set-Cookie": set_cookies(("accesstoken", fazer_jwt({"token": UUID})))})
    proxima = spider.apos_login(resposta(corpo, headers=headers))

    assert json.loads(proxima.body)["pagina"] == 1
    assert proxima.headers["Accesstoken"].decode() == UUID
    assert proxima.headers["Loggeduser"].decode() == "1"
    assert "siteVersion=" in proxima.url


def test_primeira_pagina_agenda_as_demais(spider):
    spider._sessao = {"codigo_usuario": 1, "codigo_externo": 2, "users": [2], "access_token": UUID}
    itens = [{"codigoExterno": str(i)} for i in range(25)]
    r = resposta({"totalRegistros": 60, "lista": itens}, cb_kwargs={"pagina": 1})

    saida = list(spider.parse_pagina(r, pagina=1))
    requests = [o for o in saida if isinstance(o, Request)]
    produtos = [o for o in saida if isinstance(o, dict)]

    assert len(produtos) == 25
    assert [json.loads(q.body)["pagina"] for q in requests] == [2, 3]  # ceil(60/25) = 3


def test_pagina_intermediaria_so_devolve_itens(spider):
    spider._sessao = {"codigo_usuario": 1, "codigo_externo": 2, "users": [2], "access_token": UUID}
    r = resposta({"totalRegistros": 60, "lista": [{"codigoExterno": "a"}]}, cb_kwargs={"pagina": 2})
    saida = list(spider.parse_pagina(r, pagina=2))
    assert saida == [{"codigoExterno": "a"}]


def test_resposta_malformada_nao_derruba_o_spider(spider):
    assert list(spider.parse_pagina(resposta({"sem": "lista"}), pagina=3)) == []