from celery import Celery

from servimed.config import get_settings

_cfg = get_settings()

app = Celery(
    "servimed",
    broker=_cfg.redis_url,
    backend=_cfg.redis_url,
    include=["servimed.queue.tasks"],
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # scraping é pesado: 1 tarefa por vez
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)