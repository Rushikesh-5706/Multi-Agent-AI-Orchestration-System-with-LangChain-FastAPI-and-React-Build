from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import groq
from langchain_groq import ChatGroq

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    pass


def build_llm() -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_retries=0,
    )


async def invoke_with_retry(
    llm: Any, messages: list[Any], publisher: Any = None, task_id: str = ""
) -> Any:
    settings = get_settings()
    max_retries = settings.LLM_MAX_RETRIES
    backoff = 2.0

    for attempt in range(max(max_retries, 5) + 1):
        try:
            return await llm.ainvoke(messages)

        except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
            raise LLMConfigurationError(
                f"Groq API key is invalid or not authorized: {exc}"
            ) from exc

        except groq.BadRequestError as exc:
            code = None
            if isinstance(exc.body, dict):
                error_obj = exc.body.get("error")
                if isinstance(error_obj, dict):
                    code = error_obj.get("code")

            if code == "tool_use_failed" and attempt < 2:
                corrective = {
                    "role": "user",
                    "content": (
                        "Your previous tool call did not match the required schema. "
                        "Please call the tool again using the exact field names and types "
                        "specified in the tool definition. Do not add extra fields."
                    ),
                }
                messages = list(messages) + [corrective]
                logger.warning("Tool schema error on attempt %d, retrying", attempt + 1)
                continue
            raise

        except groq.RateLimitError as exc:
            rate_limit_max = max(max_retries, 5)
            if attempt >= rate_limit_max:
                raise

            wait = None
            if exc.response is not None and "retry-after" in exc.response.headers:
                try:
                    wait = float(exc.response.headers["retry-after"])
                except (ValueError, TypeError):
                    wait = None

            if wait is None:
                match = re.search(r"try again in (\d+(?:\.\d+)?)s", str(exc), re.IGNORECASE)
                if match:
                    wait = float(match.group(1))

            if wait is None:
                wait = backoff * (2**attempt)

            wait = min(wait, 60.0)

            if publisher and task_id:
                from app.core.enums import EventType

                await publisher.emit(
                    task_id=task_id,
                    event_type=EventType.AGENT_ACTION,
                    agent_name="system",
                    message=f"Rate limit reached; waiting {wait:.0f}s before retry.",
                    payload={"kind": "rate_limit_wait", "wait_seconds": wait},
                )
            logger.warning("Rate limit on attempt %d, waiting %.1fs", attempt + 1, wait)
            await asyncio.sleep(wait)
            continue

        except (
            groq.APIConnectionError,
            groq.APITimeoutError,
            groq.InternalServerError,
        ) as exc:
            if attempt >= max_retries:
                raise
            wait = min(backoff * (2**attempt), 60.0)
            logger.warning(
                "Transient LLM error '%s' on attempt %d, retrying in %.1fs",
                type(exc).__name__,
                attempt + 1,
                wait,
            )
            await asyncio.sleep(wait)
            continue

    raise RuntimeError("Exhausted retries without a result or a raised exception.")
