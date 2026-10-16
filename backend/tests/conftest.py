from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest

from app.db.base import Base
from app.db.session import dispose_engine, get_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_API_KEY", "test-key-groq")
os.environ.setdefault("OPENWEATHER_API_KEY", "test-key-weather")
os.environ.setdefault("TOOL_SIMULATED_DELAY_SECONDS", "0")


@pytest.fixture(autouse=True)
async def setup_test_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[None, None]:
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")

    from app.core.config import get_settings

    get_settings.cache_clear()
    await dispose_engine()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def eager_celery() -> Generator[None, None, None]:
    from app.worker.celery_app import celery_app

    old_value = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        yield
    finally:
        celery_app.conf.task_always_eager = old_value
