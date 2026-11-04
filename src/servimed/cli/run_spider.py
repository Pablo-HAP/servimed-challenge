"""Script de execução
    uv run python -m servimed.cli.run_spider --usuario EMAIL --saida output/produtos.json

Credenciais: --usuario/--senha, ou SERVIMED_USER/SERVIMED_PASSWORD (.env ou
ambiente). Sem senha em lugar nenhum, ela é pedida no terminal (não fica no
histórico do shell). Na fila, prefira passar as credenciais pelo ambiente do
subprocesso em vez de argumentos, que aparecem na lista de processos.

Códigos de saída (usados pela task Celery):
    0  sucesso
    1  erro (login com problema, páginas com falha, execução interrompida)
    2  credenciais inválidas
"""

from __future__ import annotations

import argparse
import logging
import sys
from getpass import getpass
from pathlib import Path

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings

from servimed.config import ConfigError, get_settings
from servimed.logging_config import setup_logging
from servimed.scraper.spiders.produtos import (
    STAT_LOGIN_ERRO,
    STAT_LOGIN_FALHOU,
    STAT_PAGINAS_COM_ERRO,
    ProdutosSpider,
)

EXIT_OK = 0
EXIT_ERRO = 1
EXIT_CREDENCIAIS_INVALIDAS = 2

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrai o catálogo de produtos da Servimed.")
    parser.add_argument("--usuario", help="padrão: SERVIMED_USER")
    parser.add_argument("--senha", help="padrão: SERVIMED_PASSWORD; se ausente, será solicitada")
    parser.add_argument("--saida", type=Path, default=Path("output/produtos.json"),
                        help="arquivo JSON de saída (padrão: output/produtos.json)")
    return parser.parse_args(argv)


def resolver_credenciais(args: argparse.Namespace) -> tuple[str, str]:
    cfg = get_settings()
    usuario = args.usuario or cfg.servimed_user or input("Usuário: ").strip()
    senha = args.senha or cfg.servimed_password or getpass("Senha: ")
    if not usuario or not senha:
        raise ConfigError("Usuário e senha são obrigatórios")
    return usuario, senha


def build_settings(saida: Path) -> Settings:
    settings = Settings()
    settings.setmodule("servimed.scraper.settings", priority="project")
    settings.set(
        "FEEDS",
        {str(saida): {"format": "json", "encoding": "utf8", "indent": 2, "overwrite": True}},
        priority="cmdline",
    )
    return settings


def codigo_de_saida(stats) -> int:
    if stats.get_value(STAT_LOGIN_FALHOU):
        return EXIT_CREDENCIAIS_INVALIDAS
    if stats.get_value(STAT_LOGIN_ERRO) or stats.get_value(STAT_PAGINAS_COM_ERRO, 0):
        return EXIT_ERRO
    if stats.get_value("finish_reason") != "finished":
        return EXIT_ERRO
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging()
    try:
        usuario, senha = resolver_credenciais(args)
    except ConfigError as exc:
        logger.error("%s", exc)
        return EXIT_ERRO

    saida = args.saida.resolve()
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.unlink(missing_ok=True)  # evita confundir com um resultado antigo

    # Um único handler de log (o nosso): o Scrapy não instala outro, o que
    # duplicaria cada linha. O nível dos loggers do Scrapy vem de SCRAPY_LOG_LEVEL.
    logging.getLogger("scrapy").setLevel(get_settings().scrapy_log_level)
    process = CrawlerProcess(build_settings(saida), install_root_handler=False)
    crawler = process.create_crawler(ProdutosSpider)
    process.crawl(crawler, usuario=usuario, senha=senha)
    process.start()

    codigo = codigo_de_saida(crawler.stats)
    if crawler.stats.get_value(STAT_LOGIN_FALHOU) or crawler.stats.get_value(STAT_LOGIN_ERRO):
        saida.unlink(missing_ok=True)  # o Scrapy cria um '[]' vazio; não deixar isso como resultado
    elif codigo == EXIT_OK:
        logger.info("Concluído. Arquivo: %s", saida)
    else:
        logger.warning("Execução incompleta: o arquivo %s é PARCIAL e não deve ser usado", saida)
    return codigo


if __name__ == "__main__":
    sys.exit(main())