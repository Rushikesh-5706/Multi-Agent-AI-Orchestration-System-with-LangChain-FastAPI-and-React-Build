from __future__ import annotations

import time

from app.worker.celery_app import celery_app


@celery_app.task(name="tools.web_search")
def task_web_search(query: str, max_results: int = 3) -> str:
    from app.core.config import get_settings
    from app.tools.web_search import run_web_search

    settings = get_settings()
    delay = settings.TOOL_SIMULATED_DELAY_SECONDS
    if delay > 0:
        time.sleep(delay)

    return run_web_search(query=query, max_results=max_results)


@celery_app.task(name="tools.get_weather")
def task_get_weather(location: str, units: str = "metric") -> str:
    from app.core.config import get_settings
    from app.tools.weather import run_get_weather

    settings = get_settings()
    delay = settings.TOOL_SIMULATED_DELAY_SECONDS
    if delay > 0:
        time.sleep(delay)

    return run_get_weather(location=location, units=units)
