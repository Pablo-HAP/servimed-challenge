"""Modelo de domínio e normalização dos produtos da Servimed.

Funções puras (sem Scrapy, sem rede): fáceis de testar. O mapeamento entre o
JSON da Servimed e o contrato do desafio está nas constantes CAMPO_*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

# --- Mapeamento Servimed -> desafio  ---
CAMPO_GTIN = "codigoBarras"
CAMPO_CODIGO = "codigoExterno"
CAMPO_DESCRICAO = "descricao"
CAMPO_PRECO_PADRAO = "valorBase"  
CAMPO_ESTOQUE = "quantidadeEstoque"

GTIN_MIN_DIGITOS = 8


class ProdutoInvalido(ValueError):
    """Item da Servimed que não pode virar um Produto válido."""


@dataclass(frozen=True)
class Produto:
    """Produto no formato esperado pela API do desafio."""

    gtin: str
    codigo: str
    descricao: str
    preco_fabrica: float
    estoque: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rejeita_vazio(valor: Any, campo: str) -> None:
    if valor is None or isinstance(valor, bool):
        raise ProdutoInvalido(f"{campo} ausente ou inválido: {valor!r}")


def parse_gtin(valor: Any) -> str:
    """Converte o GTIN para string de dígitos (a Servimed envia como número)."""
    _rejeita_vazio(valor, "gtin")
    if isinstance(valor, float):
        if not valor.is_integer():
            raise ProdutoInvalido(f"gtin inválido: {valor!r}")
        valor = int(valor)
    texto = str(valor).strip()
    if not (texto.isascii() and texto.isdigit()):
        raise ProdutoInvalido(f"gtin inválido: {valor!r}")
    if len(texto) < GTIN_MIN_DIGITOS:
        raise ProdutoInvalido(f"gtin com menos de {GTIN_MIN_DIGITOS} dígitos: {texto!r}")
    if int(texto) == 0:
        raise ProdutoInvalido("gtin zerado")
    return texto


def parse_preco(valor: Any) -> float:
    """Aceita número ou texto ('R$ 1.234,56') e devolve float não negativo."""
    _rejeita_vazio(valor, "preco")
    if isinstance(valor, (int, float, Decimal)):
        texto = str(valor)
    else:
        texto = str(valor).strip().replace("R$", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ProdutoInvalido(f"preco inválido: {valor!r}") from exc
    if not numero.is_finite() or numero < 0:
        raise ProdutoInvalido(f"preco inválido: {valor!r}")
    return float(numero)


def parse_estoque(valor: Any) -> int:
    """Estoque inteiro e não negativo (0 é válido)."""
    _rejeita_vazio(valor, "estoque")
    if isinstance(valor, float):
        if not valor.is_integer():
            raise ProdutoInvalido(f"estoque inválido: {valor!r}")
        valor = int(valor)
    try:
        numero = int(str(valor).strip())
    except ValueError as exc:
        raise ProdutoInvalido(f"estoque inválido: {valor!r}") from exc
    if numero < 0:
        raise ProdutoInvalido(f"estoque negativo: {numero}")
    return numero


def _texto_obrigatorio(valor: Any, campo: str) -> str:
    _rejeita_vazio(valor, campo)
    texto = " ".join(str(valor).split())  # tira bordas e espaços repetidos
    if not texto:
        raise ProdutoInvalido(f"{campo} vazio")
    return texto


def normalizar_produto(bruto: Mapping[str, Any], campo_preco: str = CAMPO_PRECO_PADRAO) -> Produto:
    """Converte um item bruto da Servimed em Produto, ou levanta ProdutoInvalido."""
    return Produto(
        gtin=parse_gtin(bruto.get(CAMPO_GTIN)),
        codigo=_texto_obrigatorio(bruto.get(CAMPO_CODIGO), "codigo"),
        descricao=_texto_obrigatorio(bruto.get(CAMPO_DESCRICAO), "descricao"),
        preco_fabrica=parse_preco(bruto.get(campo_preco)),
        estoque=parse_estoque(bruto.get(CAMPO_ESTOQUE)),
    )