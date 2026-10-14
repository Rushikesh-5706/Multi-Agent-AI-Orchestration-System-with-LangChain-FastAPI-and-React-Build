from __future__ import annotations

import logging
import logging.config

from fastapi import APIRouter, Response

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    db_status = "up"
    redis_status = "up"
    overall_ok = True

    try:
        from sqlalchemy import text

        from app.db.session import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Health check: database down: %s", exc)
        db_status = "down"
        overall_ok = False

    try:
        import redis.asyncio as aioredis

        from app.core.config import get_settings

        settings = get_settings()
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception as exc:
        logger.warning("Health check: redis down: %s", exc)
        redis_status = "down"
        overall_ok = False

    body = {
        "status": "ok" if overall_ok else "degraded",
        "database": db_status,
        "redis": redis_status,
    }
    status_code = 200 if overall_ok else 503
    return Response(
        content=__import__("json").dumps(body),
        status_code=status_code,
        media_type="application/json",
    )
