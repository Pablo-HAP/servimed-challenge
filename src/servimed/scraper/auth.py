"""Extração do token de sessão a partir dos cookies da resposta do login.

A Servimed devolve o cookie `accesstoken` (um JWT). O campo `token` dentro do
payload desse JWT (um UUID) precisa ser reenviado no header `accesstoken` das
chamadas seguintes. O JWT é só decodificado (base64), nunca validado: quem
valida a assinatura é o servidor.
"""

from __future__ import annotations

import base64
import json
from http.cookies import CookieError, SimpleCookie
from typing import Iterable

COOKIE_ACCESS_TOKEN = "accesstoken"
CAMPO_TOKEN = "token"


class SessaoInvalida(RuntimeError):
    """A resposta do login não trouxe o que é preciso para abrir a sessão."""


def valor_cookie(set_cookie_headers: Iterable[bytes | str], nome: str) -> str | None:
    """Valor do cookie `nome` nos headers Set-Cookie. Se repetido, vale o último."""
    valor = None
    for header in set_cookie_headers:
        texto = header.decode("latin-1") if isinstance(header, bytes) else header
        cookie: SimpleCookie = SimpleCookie()
        try:
            cookie.load(texto)
        except CookieError:
            continue
        if nome in cookie:
            valor = cookie[nome].value
    return valor


def decodificar_payload_jwt(jwt: str) -> dict:
    partes = jwt.split(".")
    if len(partes) != 3:
        raise SessaoInvalida("o cookie accesstoken não parece um JWT")
    corpo = partes[1]
    corpo += "=" * (-len(corpo) % 4)  # base64url sem padding
    try:
        payload = json.loads(base64.urlsafe_b64decode(corpo))
    except ValueError as exc:  # inclui erro de base64, utf-8 e JSON
        raise SessaoInvalida("payload do JWT não pôde ser decodificado") from exc
    if not isinstance(payload, dict):
        raise SessaoInvalida("payload do JWT não é um objeto")
    return payload


def extrair_access_token(set_cookie_headers: Iterable[bytes | str]) -> str:
    """UUID a ser enviado no header `accesstoken`."""
    jwt = valor_cookie(set_cookie_headers, COOKIE_ACCESS_TOKEN)
    if not jwt:
        raise SessaoInvalida(f"cookie {COOKIE_ACCESS_TOKEN} ausente na resposta do login")
    token = decodificar_payload_jwt(jwt).get(CAMPO_TOKEN)
    if not token:
        raise SessaoInvalida(f"campo '{CAMPO_TOKEN}' ausente no JWT do {COOKIE_ACCESS_TOKEN}")
    return str(token)