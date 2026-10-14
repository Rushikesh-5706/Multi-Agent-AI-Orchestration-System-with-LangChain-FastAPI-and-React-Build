from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig

from app.agents.events import EventPublisher
from app.agents.llm import LLMConfigurationError, invoke_with_retry
from app.agents.prompts import PLANNER_SYSTEM_PROMPT
from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.enums import EventType
from app.tools.registry import get_tool_catalog_text

logger = logging.getLogger(__name__)


async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {})
    publisher: EventPublisher = configurable["publisher"]
    llm = configurable["llm"]
    settings = get_settings()
    task_id = state["task_id"]
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    system_prompt = PLANNER_SYSTEM_PROMPT.format(
        today=today,
        tool_catalog=get_tool_catalog_text(),
        max_plan_steps=settings.MAX_PLAN_STEPS,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": state["prompt"]},
    ]

    plan: list[str] | None = None
    last_error = ""

    for attempt in range(2):
        try:
            response = await invoke_with_retry(llm, messages, publisher, task_id)
            content = response.content if hasattr(response, "content") else str(response)
            plan = _parse_plan(content, settings.MAX_PLAN_STEPS)
            if plan is not None:
                break
            last_error = f"Could not parse plan from response: {content[:200]}"
            logger.warning("Plan parse failure on attempt %d: %s", attempt + 1, last_error)
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response could not be parsed as a JSON array. "
                        "Return only a JSON array of step strings, nothing else. "
                        'Example: ["Search for X", "Calculate Y"]'
                    ),
                }
            )
        except LLMConfigurationError:
            raise
        except Exception as exc:
            last_error = str(exc)
            logger.error("Planner LLM error: %s", exc)
            if attempt == 1:
                break

    if plan is None:
        await publisher.emit(
            task_id=task_id,
            event_type=EventType.ERROR,
            agent_name="Planner",
            message="Plan parsing failed; using single-step fallback.",
            payload={"kind": "plan_parse_failure", "detail": last_error, "fatal": False},
        )
        plan = [state["prompt"]]

    await publisher.emit(
        task_id=task_id,
        event_type=EventType.AGENT_THOUGHT,
        agent_name="Planner",
        message=f"Created plan with {len(plan)} step(s).",
        payload={"kind": "plan", "steps": plan},
    )

    return {
        "plan": plan,
        "current_step": 0,
        "messages": [{"agent": "Planner", "content": f"Plan: {plan}"}],
    }


def _parse_plan(content: str, max_steps: int) -> list[str] | None:
    content = content.strip()

    array_match = re.search(r"\[.*\]", content, re.DOTALL)
    if array_match:
        try:
            parsed = json.loads(array_match.group(0))
            if isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
                return parsed[:max_steps] if len(parsed) > 0 else None
        except json.JSONDecodeError:
            pass

    obj_match = re.search(r"\{.*\}", content, re.DOTALL)
    if obj_match:
        try:
            parsed = json.loads(obj_match.group(0))
            if isinstance(parsed, dict) and "steps" in parsed:
                steps = parsed["steps"]
                if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                    return steps[:max_steps] if len(steps) > 0 else None
        except json.JSONDecodeError:
            pass

    return None
