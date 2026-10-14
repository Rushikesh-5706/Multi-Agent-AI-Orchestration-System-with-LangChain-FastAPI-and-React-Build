from __future__ import annotations

from unittest.mock import patch

import responses

from app.tools.weather import _GEO_URL, _WEATHER_URL
from app.worker.celery_app import celery_app
from app.worker.tasks import task_get_weather, task_web_search


def test_celery_task_web_search_eager():
    celery_app.conf.update(task_always_eager=True)

    fake_results = [{"title": "Test Title", "href": "https://example.com", "body": "Test Snippet"}]

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.return_value = fake_results

        res = task_web_search.delay(query="python", max_results=1)
        assert res.successful()
        result_text = res.get()
        assert "1. Test Title" in result_text
        assert "https://example.com" in result_text


@responses.activate
def test_celery_task_weather_eager(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key-celery")
    from app.core.config import get_settings

    get_settings.cache_clear()

    celery_app.conf.update(task_always_eager=True)

    responses.add(
        responses.GET,
        _GEO_URL,
        json=[{"name": "Kyoto", "lat": 35.0116, "lon": 135.7681, "country": "JP"}],
        status=200,
    )
    responses.add(
        responses.GET,
        _WEATHER_URL,
        json={
            "name": "Kyoto",
            "weather": [{"description": "few clouds"}],
            "main": {"temp": 21.0, "feels_like": 20.5, "humidity": 55},
            "wind": {"speed": 3.0},
            "sys": {"country": "JP"},
        },
        status=200,
    )

    res = task_get_weather.delay(location="Kyoto, JP", units="metric")
    assert res.successful()
    result_text = res.get()
    assert "Weather for Kyoto, JP:" in result_text
    assert "Temperature: 21.0C" in result_text

    get_settings.cache_clear()
