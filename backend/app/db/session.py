from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def verify_db_connection(max_attempts: int = 5, delay: float = 2.0) -> None:
    from sqlalchemy import text

    engine = get_engine()
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection verified")
            return
        except Exception as exc:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"Cannot reach PostgreSQL after {max_attempts} attempts: {exc}"
                ) from exc
            logger.warning("Database not ready (attempt %d/%d): %s", attempt, max_attempts, exc)
            await asyncio.sleep(delay)


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _sessionmaker = None
