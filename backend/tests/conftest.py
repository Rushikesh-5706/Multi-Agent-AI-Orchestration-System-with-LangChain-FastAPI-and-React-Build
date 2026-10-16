from __future__ import annotations

import os
from collections.abc import Generator

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_API_KEY", "test-key-groq")
os.environ.setdefault("OPENWEATHER_API_KEY", "test-key-weather")
os.environ.setdefault("TOOL_SIMULATED_DELAY_SECONDS", "0")


@pytest.fixture(autouse=True)
def eager_celery() -> Generator[None, None, None]:
    from app.worker.celery_app import celery_app

    old_value = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        yield
    finally:
        celery_app.conf.task_always_eager = old_value
