from __future__ import annotations

import logging
from typing import Literal

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"
_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def _unit_labels(units: str) -> tuple[str, str, str]:
    if units == "imperial":
        return "F", "mph", "imperial"
    return "C", "m/s", "metric"


def run_get_weather(location: str, units: Literal["metric", "imperial"] = "metric") -> str:
    settings = get_settings()

    api_key = settings.OPENWEATHER_API_KEY
    if not api_key:
        return (
            "Error: OPENWEATHER_API_KEY is not configured. "
            "Weather data cannot be retrieved. Report to the user that weather is unavailable."
        )

    temp_unit, speed_unit, units_param = _unit_labels(units)
    connect_timeout = 5
    read_timeout = 10

    try:
        geo_resp = requests.get(
            _GEO_URL,
            params={"q": location, "limit": 1, "appid": api_key},
            timeout=(connect_timeout, read_timeout),
        )
    except requests.exceptions.ConnectTimeout:
        return (
            "Error: Connection to the OpenWeather geocoding API timed out. "
            "Retry once; if it fails again, report that weather is unavailable."
        )
    except requests.exceptions.ConnectionError as exc:
        return (
            f"Error: Cannot reach the OpenWeather API ({exc}). "
            "Check network connectivity and retry."
        )
    except requests.exceptions.Timeout:
        return "Error: OpenWeather geocoding request timed out. Retry with the same location."

    if geo_resp.status_code == 401:
        return (
            "Error: OpenWeather API key rejected (HTTP 401). "
            "Do not retry this call. Report to the user that the weather API is not authorized."
        )
    if geo_resp.status_code == 429:
        return (
            "Error: OpenWeather API rate limit reached (HTTP 429). "
            "Wait before retrying, or report that weather is temporarily unavailable."
        )
    if geo_resp.status_code >= 500:
        return (
            f"Error: OpenWeather server error (HTTP {geo_resp.status_code}). "
            "Retry once; if it fails again, report the outage."
        )
    if geo_resp.status_code != 200:
        return (
            f"Error: Unexpected geocoding response (HTTP {geo_resp.status_code}). "
            "Try a different location format."
        )

    try:
        geo_data = geo_resp.json()
    except ValueError:
        return (
            "Error: OpenWeather returned a non-JSON geocoding response. "
            "Retry or report the API issue."
        )

    if not isinstance(geo_data, list) or len(geo_data) == 0:
        return (
            f"Error: Location '{location}' was not found by OpenWeather. "
            "Try a more specific location name including the country code, "
            "for example 'Paris, FR' or 'Springfield, IL, US'."
        )

    place = geo_data[0]
    try:
        lat = float(place["lat"])
        lon = float(place["lon"])
        resolved_name = place.get("name", location)
        country = place.get("country", "")
    except (KeyError, TypeError, ValueError):
        return (
            "Error: Unexpected geocoding response shape from OpenWeather. "
            "Retry with a different location format."
        )

    try:
        weather_resp = requests.get(
            _WEATHER_URL,
            params={
                "lat": lat,
                "lon": lon,
                "units": units_param,
                "appid": api_key,
            },
            timeout=(connect_timeout, read_timeout),
        )
    except requests.exceptions.ConnectTimeout:
        return (
            "Error: Connection to the OpenWeather weather endpoint timed out. "
            "Retry once; if it fails again, report that weather is unavailable."
        )
    except requests.exceptions.ConnectionError as exc:
        return f"Error: Cannot reach the OpenWeather weather endpoint ({exc})."
    except requests.exceptions.Timeout:
        return "Error: OpenWeather weather request timed out. Retry with the same location."

    if weather_resp.status_code == 401:
        return (
            "Error: OpenWeather API key rejected (HTTP 401). "
            "Do not retry. Report that the weather API is not authorized."
        )
    if weather_resp.status_code == 404:
        return (
            f"Error: No weather data found for coordinates ({lat}, {lon}). "
            "Try a different location."
        )
    if weather_resp.status_code == 429:
        return "Error: OpenWeather API rate limit reached (HTTP 429). Retry after a delay."
    if weather_resp.status_code >= 500:
        return (
            f"Error: OpenWeather server error (HTTP {weather_resp.status_code}). "
            "Retry once; if it fails again, report the outage."
        )
    if weather_resp.status_code != 200:
        return f"Error: Unexpected weather response (HTTP {weather_resp.status_code})."

    try:
        w = weather_resp.json()
    except ValueError:
        return (
            "Error: OpenWeather returned a non-JSON weather response. "
            "Retry or report the API issue."
        )

    try:
        temp = w["main"]["temp"]
        feels_like = w["main"]["feels_like"]
        humidity = w["main"]["humidity"]
        wind_speed = w["wind"]["speed"]
        description = w["weather"][0]["description"].capitalize()
        city_name = w.get("name", resolved_name)
        sys_country = w.get("sys", {}).get("country", country)
    except (KeyError, IndexError, TypeError):
        return (
            "Error: Unexpected JSON shape in OpenWeather weather response. "
            "The API may have changed its format."
        )

    return (
        f"Weather for {city_name}, {sys_country}:\n"
        f"  Condition: {description}\n"
        f"  Temperature: {temp}{temp_unit} (feels like {feels_like}{temp_unit})\n"
        f"  Humidity: {humidity}%\n"
        f"  Wind speed: {wind_speed} {speed_unit}"
    )
