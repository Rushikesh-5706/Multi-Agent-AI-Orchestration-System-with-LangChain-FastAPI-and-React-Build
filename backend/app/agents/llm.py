from __future__ import annotations

import asyncio
import logging
import re

import groq
from langchain_groq import ChatGroq

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    pass


class LLMRateLimitError(Exception):
    pass


def build_llm() -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_retries=0,
    )


async def invoke_with_retry(llm, messages: list, publisher=None, task_id: str = "") -> object:
    settings = get_settings()
    max_retries = settings.LLM_MAX_RETRIES
    backoff = 2.0

    for attempt in range(max_retries + 1):
        try:
            return await llm.ainvoke(messages)

        except groq.AuthenticationError as exc:
            raise LLMConfigurationError(
                f"Groq API key is invalid or not authorized: {exc}"
            ) from exc

        except groq.BadRequestError as exc:
            exc_str = str(exc).lower()
            if "tool_use_failed" in exc_str or "tool_calls" in exc_str or "tool" in exc_str:
                if attempt < 2:
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
            wait = backoff * (2**attempt)
            exc_str = str(exc)
            match = re.search(r"(?:retry.after|try again in)[:\s]+(\d+(?:\.\d+)?)", exc_str)
            if match:
                wait = max(float(match.group(1)) + 0.5, 2.0)

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
            wait = backoff * (2**attempt)
            logger.warning(
                "Transient LLM error '%s' on attempt %d, retrying in %.1fs",
                type(exc).__name__,
                attempt + 1,
                wait,
            )
            await asyncio.sleep(wait)
            continue

    raise RuntimeError("Exhausted retries without a result or a raised exception.")
