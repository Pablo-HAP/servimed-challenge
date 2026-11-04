"""Settings do Scrapy. Valores variáveis vêm do .env via servimed.config."""

from servimed.config import get_settings
from servimed.logging_config import DATE_FORMAT, LOG_FORMAT

_cfg = get_settings()

BOT_NAME = "servimed"
SPIDER_MODULES = ["servimed.scraper.spiders"]
NEWSPIDER_MODULE = "servimed.scraper.spiders"

# Respeito ao servidor: poucas requisições simultâneas e pequeno atraso.
ROBOTSTXT_OBEY = _cfg.scrapy_robotstxt_obey
DOWNLOAD_DELAY = _cfg.scrapy_download_delay
CONCURRENT_REQUESTS = _cfg.scrapy_concurrent_requests
CONCURRENT_REQUESTS_PER_DOMAIN = _cfg.scrapy_concurrent_requests
DOWNLOAD_TIMEOUT = 30

# Retry para erros transitórios nas páginas. O login desliga o retry por request.
RETRY_ENABLED = True
RETRY_TIMES = 3

# Sessão por cookie. COOKIES_DEBUG fica desligado: ele imprimiria tokens no log.
COOKIES_ENABLED = True
COOKIES_DEBUG = False
TELNETCONSOLE_ENABLED = False

if _cfg.scrapy_user_agent:
    USER_AGENT = _cfg.scrapy_user_agent

# Mesmo formato de log do restante do projeto.
LOG_LEVEL = _cfg.scrapy_log_level
LOG_FORMAT = LOG_FORMAT
LOG_DATEFORMAT = DATE_FORMAT

ITEM_PIPELINES = {
    "servimed.scraper.pipelines.ValidaProdutoPipeline": 300,
}

# Campo da Servimed usado como preco_fabrica (lido pela pipeline).
SERVIMED_PRICE_FIELD = _cfg.servimed_price_field

FEED_EXPORT_ENCODING = "utf-8"