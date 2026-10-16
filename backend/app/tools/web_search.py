from __future__ import annotations

import logging
import textwrap

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " [truncated]"


def run_web_search(query: str, max_results: int = 3) -> str:
    settings = get_settings()
    max_chars = settings.MAX_TOOL_OUTPUT_CHARS

    try:
        from ddgs import DDGS
        from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
    except ImportError:
        return "Error: The ddgs package is not installed. Cannot perform web search."

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except RatelimitException:
        return (
            "Error: DuckDuckGo rate limit reached. Wait a moment and retry with the same "
            "query, or rephrase the query."
        )
    except TimeoutException:
        return "Error: Web search timed out. Retry with a simpler query, or try a different tool."
    except DDGSException as exc:
        logger.warning("DuckDuckGo search error for query '%s': %s", query, exc)
        return (
            f"Error: Web search failed ({type(exc).__name__}). Retry with a different query or "
            "use another tool to gather the information."
        )
    except Exception as exc:
        logger.warning("Unexpected search error for query '%s': %s", query, exc, exc_info=True)
        return f"Error: Web search failed unexpectedly ({type(exc).__name__}). Retry with a different query."

    if not results:
        return (
            f"No results found for the query '{query}'. "
            "Try rephrasing the query or searching for a related term."
        )

    lines: list[str] = []
    for i, r in enumerate(results, start=1):
        title = r.get("title", "").strip()
        url = r.get("href", "").strip()
        snippet = r.get("body", "").strip()
        snippet = textwrap.shorten(snippet, width=300, placeholder="...")
        lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

    output = "\n\n".join(lines)
    return _truncate(output, max_chars)
