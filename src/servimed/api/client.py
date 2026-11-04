"""Cliente da API do desafio: OAuth (signup/token) e envio de produtos em lotes.

Classificação dos erros, usada pela task Celery para decidir sobre retentativas:
- ApiClientError: 4xx (credencial da API inválida, corpo recusado). Repetir não adianta.
- ApiTransientError: timeout, falha de conexão, 5xx, 408 ou 429. Vale tentar de novo.

Nenhuma senha ou token é registrada em log.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

import requests

log = logging.getLogger(__name__)

# Renova o token um pouco antes de expirar.
MARGEM_EXPIRACAO_S = 30


class ApiError(Exception):
    """Erro base do cliente da API do desafio."""


class ApiClientError(ApiError):
    """Erro 4xx (credencial, validação). Não vale retentar."""


class ApiTransientError(ApiError):
    """Falha de rede, timeout, 5xx, 408 ou 429. Vale retentar."""


class DesafioApiClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 10,
        batch_size: int = 500,
        session: requests.Session | None = None,
    ):
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._batch_size = max(1, batch_size)
        self._session = session or requests.Session()
        self._token: str | None = None
        self._expira_em = 0.0

    # ---------- HTTP de baixo nível ----------
    def _chamar(self, metodo: str, caminho: str, **kwargs: Any) -> requests.Response:
        try:
            return self._session.request(
                metodo, f"{self._base}{caminho}", timeout=self._timeout, **kwargs
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ApiTransientError(f"{metodo} {caminho}: {type(exc).__name__}") from exc

    @staticmethod
    def _checar(resp: requests.Response, contexto: str, incluir_corpo: bool = True) -> None:
        if resp.ok:
            return
        status = resp.status_code
        if status >= 500 or status in (408, 429):
            raise ApiTransientError(f"{contexto}: HTTP {status}")
        # Respostas de erro de validação podem repetir o corpo enviado (com a senha):
        # nas chamadas de autenticação o corpo não é incluído na mensagem.
        detalhe = f" {resp.text[:300]}" if incluir_corpo else ""
        raise ApiClientError(f"{contexto}: HTTP {status}{detalhe}")

    # ---------- autenticação ----------
    def _guardar_token(self, dados: Any) -> None:
        try:
            self._token = dados["access_token"]
            expira_em_s = int(dados.get("expires_in") or 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiClientError("resposta de autenticação inesperada") from exc
        if expira_em_s > 0:
            self._expira_em = time.monotonic() + expira_em_s - MARGEM_EXPIRACAO_S
        else:
            self._expira_em = float("inf")  # validade desconhecida: confia no 401

    def _obter_token(self) -> None:
        resp = self._chamar(
            "POST",
            "/oauth/token",
            data={"username": self._username, "password": self._password},
        )
        self._checar(resp, "token", incluir_corpo=False)
        self._guardar_token(resp.json())

    def _signup(self) -> None:
        resp = self._chamar(
            "POST",
            "/oauth/signup",
            json={"username": self._username, "password": self._password},
        )
        self._checar(resp, "signup", incluir_corpo=False)
        # O signup também devolve um token (access_token, token_type, expires_in).
        self._guardar_token(resp.json())
        log.info("usuário da API criado (usuário=%s)", self._username)

    def autenticar(self) -> None:
        """Obtém um token. Se o login for recusado, tenta criar o usuário e repete."""
        self._token = None
        try:
            self._obter_token()
            return
        except ApiClientError:
            log.info("login na API recusado; tentando criar o usuário")
        try:
            self._signup()
        except ApiClientError:
            log.info("signup recusado (usuário provavelmente já existe)")
        if self._token is None:
            self._obter_token()  # se falhar de novo: credenciais da API inválidas

    # ---------- chamadas autenticadas ----------
    def _request(self, metodo: str, caminho: str, **kwargs: Any) -> requests.Response:
        if not self._token or time.monotonic() >= self._expira_em:
            self.autenticar()
        resp = None
        for tentativa in (1, 2):
            resp = self._chamar(
                metodo,
                caminho,
                headers={"Authorization": f"Bearer {self._token}"},
                **kwargs,
            )
            if resp.status_code == 401 and tentativa == 1:
                log.info("token recusado (401); renovando")
                self.autenticar()
                continue
            break
        self._checar(resp, f"{metodo} {caminho}")
        return resp

    def enviar_produtos(self, produtos: Sequence[dict[str, Any]]) -> int:
        """Envia os produtos em lotes para POST /produto e devolve quantos foram aceitos.

        Atenção: se a API não deduplicar, reenviar um lote que já foi aceito duplica
        os registros. Por isso a task não deve repetir o envio depois de um sucesso.
        """
        total = len(produtos)
        enviados = 0
        for inicio in range(0, total, self._batch_size):
            lote = list(produtos[inicio : inicio + self._batch_size])
            resp = self._request("POST", "/produto", json=lote)
            try:
                aceitos = len(resp.json())
            except (ValueError, TypeError):
                aceitos = len(lote)
            if aceitos != len(lote):
                log.warning("lote com %s itens, API devolveu %s", len(lote), aceitos)
            enviados += aceitos
            log.info("produtos enviados: %s/%s", enviados, total)
        return enviados