from __future__ import annotations

from unittest.mock import patch

from app.tools.web_search import run_web_search


def test_web_search_success():
    fake_results = [
        {
            "title": "Tokyo Weather Forecast",
            "href": "https://example.org/tokyo",
            "body": "Mild temperatures around 18C and partly cloudy skies.",
        },
        {
            "title": "Visit Tokyo Guide",
            "href": "https://example.org/guide",
            "body": "Essential packing tips for travelers visiting Tokyo in autumn.",
        },
    ]

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.return_value = fake_results

        output = run_web_search("weather tokyo", max_results=2)
        assert "1. Tokyo Weather Forecast" in output
        assert "https://example.org/tokyo" in output
        assert "Mild temperatures around 18C" in output
        assert "2. Visit Tokyo Guide" in output


def test_web_search_empty():
    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.return_value = []

        output = run_web_search("nonexistent query 123456789")
        assert "No results found" in output
        assert not output.startswith("Error:")


def test_web_search_ratelimit():
    from ddgs.exceptions import RatelimitException

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.side_effect = RatelimitException("Ratelimit reached: 202 Ratelimit")

        output = run_web_search("rate limit test")
        assert output.startswith("Error: DuckDuckGo rate limit reached.")


def test_web_search_timeout():
    from ddgs.exceptions import TimeoutException

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.side_effect = TimeoutException("Connection timed out")

        output = run_web_search("timeout test")
        assert output.startswith("Error: Web search timed out.")


def test_web_search_generic_error():
    from ddgs.exceptions import DDGSException

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.side_effect = DDGSException("Something unexpected happened")

        output = run_web_search("generic error test")
        assert output.startswith("Error: Web search failed (DDGSException).")


def test_web_search_truncation(monkeypatch):
    monkeypatch.setenv("MAX_TOOL_OUTPUT_CHARS", "100")
    from app.core.config import get_settings

    get_settings.cache_clear()

    fake_results = [
        {
            "title": "A" * 80,
            "href": "https://example.org/long",
            "body": "B" * 150,
        }
    ]

    with patch("ddgs.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value.__enter__.return_value
        instance.text.return_value = fake_results

        output = run_web_search("truncation test")
        assert len(output) <= 120
        assert "[truncated]" in output

    get_settings.cache_clear()
