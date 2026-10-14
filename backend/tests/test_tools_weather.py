from __future__ import annotations

import requests
import responses

from app.tools.weather import _GEO_URL, _WEATHER_URL, run_get_weather


def test_weather_missing_api_key(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()

    output = run_get_weather("Tokyo, JP")
    assert output.startswith("Error: OPENWEATHER_API_KEY is not configured.")
    get_settings.cache_clear()


@responses.activate
def test_weather_success(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key-123")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(
        responses.GET,
        _GEO_URL,
        json=[{"name": "Tokyo", "lat": 35.6762, "lon": 139.6503, "country": "JP"}],
        status=200,
    )
    responses.add(
        responses.GET,
        _WEATHER_URL,
        json={
            "name": "Tokyo",
            "weather": [{"description": "clear sky"}],
            "main": {"temp": 18.5, "feels_like": 17.8, "humidity": 60},
            "wind": {"speed": 4.2},
            "sys": {"country": "JP"},
        },
        status=200,
    )

    output = run_get_weather("Tokyo, JP")
    assert "Weather for Tokyo, JP:" in output
    assert "Condition: Clear sky" in output
    assert "Temperature: 18.5C (feels like 17.8C)" in output
    assert "Humidity: 60%" in output
    assert "Wind speed: 4.2 m/s" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_imperial_units(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key-123")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(
        responses.GET,
        _GEO_URL,
        json=[{"name": "New York", "lat": 40.7128, "lon": -74.0060, "country": "US"}],
        status=200,
    )
    responses.add(
        responses.GET,
        _WEATHER_URL,
        json={
            "name": "New York",
            "weather": [{"description": "partly cloudy"}],
            "main": {"temp": 68.0, "feels_like": 67.2, "humidity": 50},
            "wind": {"speed": 8.5},
            "sys": {"country": "US"},
        },
        status=200,
    )

    output = run_get_weather("New York, NY, US", units="imperial")
    assert "Temperature: 68.0F (feels like 67.2F)" in output
    assert "Wind speed: 8.5 mph" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_401_rejected_key(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "bad-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(responses.GET, _GEO_URL, status=401)

    output = run_get_weather("London, GB")
    assert output.startswith("Error: OpenWeather API key rejected (HTTP 401).")
    assert "Do not retry" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_location_not_found(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(responses.GET, _GEO_URL, json=[], status=200)

    output = run_get_weather("FakeCityXYZ")
    assert "Error: Location 'FakeCityXYZ' was not found" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_429_rate_limit(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(responses.GET, _GEO_URL, status=429)

    output = run_get_weather("Berlin, DE")
    assert "HTTP 429" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_500_server_error(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(responses.GET, _GEO_URL, status=503)

    output = run_get_weather("Sydney, AU")
    assert "HTTP 503" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_non_json(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(responses.GET, _GEO_URL, body="<html>Bad Gateway</html>", status=200)

    output = run_get_weather("Rome, IT")
    assert "non-JSON" in output
    get_settings.cache_clear()


@responses.activate
def test_weather_timeout(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    responses.add(
        responses.GET,
        _GEO_URL,
        body=requests.exceptions.ConnectTimeout("Connection timed out"),
    )

    output = run_get_weather("Madrid, ES")
    assert "timed out" in output
    get_settings.cache_clear()
