from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import get_settings
from app.core.enums import EventType
from app.tools.registry import ToolSpec, get_tool_registry

logger = logging.getLogger(__name__)


async def execute_tool(
    spec: ToolSpec,
    arguments: dict,
    publisher,
    task_id: str,
) -> str:
    settings = get_settings()

    try:
        validated = spec.args_schema(**arguments)
        validated_args = validated.model_dump()
    except Exception as exc:
        msg = f"Error: Tool arguments failed validation for '{spec.name}': {exc}"
        return msg

    celery_task_id = None
    start_ms = time.monotonic()

    await publisher.emit(
        task_id=task_id,
        event_type=EventType.TOOL_INVOCATION,
        agent_name="tool_executor",
        message=f"Invoking tool '{spec.name}'",
        payload={
            "tool": spec.name,
            "arguments": validated_args,
            "execution": spec.execution,
        },
    )

    if spec.execution == "celery":
        import app.worker.tasks  # noqa: F401
        from app.worker.celery_app import celery_app

        try:
            task_fn = celery_app.tasks.get(spec.celery_task_name)
            if task_fn is not None:
                async_result = await asyncio.to_thread(
                    lambda: task_fn.apply_async(kwargs=validated_args)
                )
            else:
                async_result = await asyncio.to_thread(
                    lambda: celery_app.send_task(spec.celery_task_name, kwargs=validated_args)
                )
            celery_task_id = async_result.id

            raw_result = await asyncio.to_thread(async_result.get, settings.TOOL_TIMEOUT_SECONDS)
            result = str(raw_result)
        except TimeoutError:
            if celery_task_id:
                try:
                    await asyncio.to_thread(
                        lambda: celery_app.control.revoke(celery_task_id, terminate=True)
                    )
                except Exception:
                    pass
            result = (
                f"Error: Tool '{spec.name}' timed out after "
                f"{settings.TOOL_TIMEOUT_SECONDS}s. "
                "Retry with a simpler query or use a different approach."
            )
        except Exception as exc:
            timeout = settings.TOOL_TIMEOUT_SECONDS
            exc_str = str(exc)
            if "timed out" in exc_str.lower() or "timeout" in exc_str.lower():
                if celery_task_id:
                    try:
                        await asyncio.to_thread(
                            lambda: celery_app.control.revoke(celery_task_id, terminate=True)
                        )
                    except Exception:
                        pass
                result = (
                    f"Error: Tool '{spec.name}' timed out after {timeout}s. "
                    "Retry with a simpler query or use a different approach."
                )
            else:
                logger.warning("Celery task error for '%s': %s", spec.name, exc)
                result = (
                    f"Error: Tool '{spec.name}' failed to execute: {exc}. Try a different approach."
                )
    else:
        try:
            result = spec.runner(**validated_args)
        except Exception as exc:
            result = f"Error: Tool '{spec.name}' raised an unexpected error: {exc}."

    duration_ms = int((time.monotonic() - start_ms) * 1000)
    truncated = _truncate(result, settings.MAX_TOOL_OUTPUT_CHARS)
    is_error = truncated.startswith("Error:")

    await publisher.emit(
        task_id=task_id,
        event_type=EventType.TOOL_RESULT,
        agent_name="tool_executor",
        message=f"Tool '{spec.name}' completed in {duration_ms}ms",
        payload={
            "tool": spec.name,
            "arguments": validated_args,
            "execution": spec.execution,
            "celery_task_id": celery_task_id,
            "result": truncated,
            "is_error": is_error,
            "duration_ms": duration_ms,
        },
    )

    return truncated


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " [truncated]"


def get_spec_by_name(name: str) -> ToolSpec | None:
    for spec in get_tool_registry():
        if spec.name == name:
            return spec
    return None
