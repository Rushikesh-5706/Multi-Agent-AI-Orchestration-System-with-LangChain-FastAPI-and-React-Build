from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.config
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.tasks import get_background_tasks
from app.api.tasks import router as tasks_router
from app.api.websocket import router as ws_router
from app.core.config import get_settings


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    settings = get_settings()

    logging.basicConfig(level=settings.LOG_LEVEL.upper())

    from app.db.session import dispose_engine, verify_db_connection

    await verify_db_connection()

    from app.db.repositories import mark_interrupted_runs_failed

    interrupted = await mark_interrupted_runs_failed()
    if interrupted:
        logging.getLogger(__name__).info(
            "Marked %d interrupted run(s) as FAILED on startup.", interrupted
        )

    yield

    for task in list(get_background_tasks()):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Multi-Agent Orchestration API",
        description="FastAPI backend for the multi-agent AI orchestration system.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(health_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(ws_router, prefix="/api")

    return app


app = create_app()
