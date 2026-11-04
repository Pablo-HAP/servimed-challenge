import pytest

from servimed.models import (
    Produto,
    ProdutoInvalido,
    normalizar_produto,
    parse_estoque,
    parse_gtin,
    parse_preco,
)


def bruto(**sobrescrever):
    base = {
        "codigoBarras": 7891234567895,
        "codigoExterno": "ABC1",
        "descricao": "  ADORLAN   50MG ",
        "valorBase": 99.53,
        "quantidadeEstoque": 364,
    }
    base.update(sobrescrever)
    return base


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        (7891234567895, "7891234567895"),
        (7891234567895.0, "7891234567895"),
        (" 7891234567895 ", "7891234567895"),
        ("12345678", "12345678"),
    ],
)
def test_gtin_valido(entrada, esperado):
    assert parse_gtin(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, "", "abc", 1234567, 0, 12.5, True, "78912-345"])
def test_gtin_invalido(entrada):
    with pytest.raises(ProdutoInvalido):
        parse_gtin(entrada)


@pytest.mark.parametrize(
    "entrada, esperado",
    [(99.53, 99.53), (10, 10.0), ("R$ 1.234,56", 1234.56), ("10,99", 10.99), ("5.5", 5.5), (0, 0.0)],
)
def test_preco_valido(entrada, esperado):
    assert parse_preco(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, "", "abc", -1, float("nan"), True])
def test_preco_invalido(entrada):
    with pytest.raises(ProdutoInvalido):
        parse_preco(entrada)


@pytest.mark.parametrize("entrada, esperado", [(0, 0), ("12", 12), (3.0, 3), (364, 364)])
def test_estoque_valido(entrada, esperado):
    assert parse_estoque(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, -1, 2.5, "x", True])
def test_estoque_invalido(entrada):
    with pytest.raises(ProdutoInvalido):
        parse_estoque(entrada)


def test_normalizar_produto_completo():
    assert normalizar_produto(bruto()) == Produto(
        gtin="7891234567895", codigo="ABC1", descricao="ADORLAN 50MG", preco_fabrica=99.53, estoque=364
    )


def test_estoque_zero_continua_valido():
    assert normalizar_produto(bruto(quantidadeEstoque=0)).estoque == 0


def test_campo_de_preco_configuravel():
    assert normalizar_produto(bruto(valorComDesconto=79.62), "valorComDesconto").preco_fabrica == 79.62


@pytest.mark.parametrize("campo", ["codigoBarras", "codigoExterno", "descricao", "valorBase", "quantidadeEstoque"])
def test_campo_ausente_invalida_o_item(campo):
    item = bruto()
    del item[campo]
    with pytest.raises(ProdutoInvalido):
        normalizar_produto(item)