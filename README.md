# servimed-challenge

Scraping autenticado do catálogo da Servimed com Scrapy, processamento assíncrono com Celery + Redis e envio dos produtos para a API do desafio da Cotefácil.

## Como rodar

**Pré-requisitos:** Python 3.11+, [uv](https://docs.astral.sh/uv/) e Docker (para o Redis).

```bash
# 1. dependências
uv sync

# 2. variáveis de ambiente
cp .env.example .env        # Windows: copy .env.example .env
# preencha SERVIMED_USER, SERVIMED_PASSWORD, DESAFIO_API_USER e DESAFIO_API_PASSWORD
```

`DESAFIO_API_USER` e `DESAFIO_API_PASSWORD` podem ser qualquer par novo: se o login na API for recusado, o cliente cria o usuário em `/oauth/signup` automaticamente.

### Nível 1: scraping direto (gera JSON local)

```bash
uv run scrapy crawl produtos -a usuario=SEU_USUARIO -a senha=SUA_SENHA -O produtos.json
```

### Nível 2: fila + worker + API

```bash
# Redis
docker compose up -d redis

# worker (em um terminal)
uv run celery -A servimed.queue.celery_app worker -l info -P solo   # -P solo é necessário no Windows

# enfileirar uma tarefa (em outro terminal, na raiz do repositório)
uv run python -m servimed.cli.enqueue                                # usa as credenciais do .env
uv run python -m servimed.cli.enqueue --usuario USER --senha PASS    # ou informando na chamada
```

No log do worker, o fim do fluxo aparece como `produtos enviados: N/N` e `Task ... succeeded`. O resultado pode ser conferido em `GET /produto` na documentação da API: https://desafio.cotefacil.net/docs

### Testes

```bash
uv run pytest -q
```

## Resumo do que foi feito

### Nível 1: Scrapy

- Spider `produtos` (Scrapy puro, sem Selenium/Playwright): faz login na API da Servimed, obtém a sessão (código do usuário e token do cookie) e percorre a listagem de produtos paginada, agendando as páginas restantes a partir do total de registros informado na primeira resposta.
- Extrai GTIN, código, descrição, preço de fábrica e estoque de cada produto e grava em JSON local.
- Credenciais recebidas por parâmetro (`-a usuario=... -a senha=...`); demais configurações vêm do `.env` por um módulo central (`config.py`), com validação e sem senhas no `repr`.
- Tratamento de erros: credencial recusada, resposta inesperada e páginas com falha são registradas em log e nas estatísticas do Scrapy.

### Nível 2: fila, worker e integração com a API

- **Fila:** Celery + Redis. A tarefa `servimed.scrape_produtos` recebe o payload `{"usuario": "...", "senha": "..."}`.
- **Worker:** executa o spider em um subprocess isolado (um por solicitação, já que o reactor do Twisted não reinicia no mesmo processo), lê o JSON gerado e envia os produtos para a API do desafio.
- **Cliente da API** (`api/client.py`): autentica em `/oauth/token`, cria o usuário em `/oauth/signup` quando o login é recusado, renova o token antes de expirar ou ao receber 401, e envia os produtos em lotes configuráveis para `POST /produto`.
- **Erros e retentativas:** falhas de rede, timeout, 5xx, 408 e 429 (`ApiTransientError`) são retentadas com backoff exponencial; erros 4xx (`ApiClientError`) e falhas do scraping (`ScrapeError`, como login recusado ou nenhum produto extraído) não são retentados.
- **Logs:** nenhuma senha ou token é registrada; a mensagem de erro das chamadas de autenticação nunca inclui o corpo da resposta.
- **Testes:** pytest cobrindo o cliente (lotes, renovação de token, classificação de erros) e a task (fluxo de sucesso e ausência de produtos).

### Nível 3

Não implementado nesta entrega.

### Limitações conhecidas

- Se um retry ocorrer depois de uma falha parcial no envio em lotes, lotes já aceitos podem ser reenviados e duplicados, caso a API não deduplique.
- Durante a execução, a senha da Servimed fica visível na lista de processos do sistema, pois é repassada ao spider por argumento.