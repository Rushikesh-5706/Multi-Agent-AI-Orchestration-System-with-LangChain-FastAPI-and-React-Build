from __future__ import annotations

import os

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "orchestrator",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.TOOL_TIMEOUT_SECONDS,
    task_time_limit=settings.TOOL_TIMEOUT_SECONDS + 30,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower()
    in ("true", "1", "yes"),
)
