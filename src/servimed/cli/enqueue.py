from __future__ import annotations

import argparse

from servimed.config import ConfigError, get_settings
from servimed.queue.tasks import scrape_produtos


def main() -> None:
    p = argparse.ArgumentParser(description="Enfileira uma tarefa de scraping da Servimed")
    p.add_argument("--usuario")
    p.add_argument("--senha")
    args = p.parse_args()

    usuario, senha = args.usuario, args.senha
    if not usuario or not senha:
        try:
            usuario, senha = get_settings().require_servimed_credentials()
        except ConfigError as exc:
            p.error(str(exc))

    resultado = scrape_produtos.delay({"usuario": usuario, "senha": senha})
    print(f"tarefa enfileirada: {resultado.id}")


if __name__ == "__main__":
    main()