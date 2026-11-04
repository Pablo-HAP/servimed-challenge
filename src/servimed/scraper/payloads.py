"""Montagem do corpo da busca de produtos."""

from __future__ import annotations

import copy
from typing import Any, Sequence

# O servidor fixa a página em 25 itens, ignorando o valor pedido. O spider usa o
# tamanho REAL da página recebida para calcular o total de páginas.
REGISTROS_POR_PAGINA = 25

# Campos que o front-end sempre envia com estes valores (levantamento da Fase 0).
# Nenhum é dado do cliente. Todos são necessários: o back-end (Oracle) quebra com
# 500 "DPI-1055: value is not a number (NaN)" quando um campo numérico não vem.
CAMPOS_FIXOS: dict[str, Any] = {
    "ordenarDecrescente": False,
    "colunaOrdenacao": "nenhuma",
    "tipoVendaId": 1,
    "fabricanteIdFiltro": 0,
    "pIIdFiltro": 0,
    "cestaPPFiltro": False,
    "codigoExterno": 0,  # o front envia 0 aqui; o código do cliente vai em clienteId
    "promocaoSelecionada": "",
    "indicadorTipoUsuario": "CLI",
    "kindUser": 0,
    "xlsx": [],
    "principioAtivo": "",
    "master": False,
    "kindSeller": 0,
    "grupoEconomico": "",
    "list": True,
}


def build_search_payload(
    pagina: int,
    codigo_usuario: int,
    codigo_externo: int,
    users: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Corpo da busca. `filtro` vazio lista o catálogo inteiro.

    `clienteId` recebe o `codigoExterno` retornado no login e `users` é uma lista
    (no login, `usuario.users`); se vier vazia, usa `[codigo_externo]`.
    """
    # deepcopy: CAMPOS_FIXOS tem uma lista ("xlsx"); sem isso, todos os payloads
    # compartilhariam o mesmo objeto.
    payload = copy.deepcopy(CAMPOS_FIXOS)
    payload.update(
        {
            "filtro": "",
            "pagina": pagina,
            "registrosPorPagina": REGISTROS_POR_PAGINA,
            "codigoUsuario": codigo_usuario,
            "clienteId": codigo_externo,
            "users": list(users) if users else [codigo_externo],
        }
    )
    return payload