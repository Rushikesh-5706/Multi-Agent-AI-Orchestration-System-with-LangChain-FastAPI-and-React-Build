from __future__ import annotations

import logging
import textwrap
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agents.events import EventPublisher
from app.agents.llm import invoke_with_retry
from app.agents.prompts import RESEARCHER_SYSTEM_PROMPT
from app.agents.state import AgentState, Finding
from app.agents.tool_executor import execute_tool, get_spec_by_name
from app.core.config import get_settings
from app.core.enums import EventType
from app.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


async def researcher_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {})
    publisher: EventPublisher = configurable["publisher"]
    llm = configurable["llm"]
    settings = get_settings()
    task_id = state["task_id"]
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    step_index = state["current_step"]
    plan = state["plan"]
    current_step = plan[step_index]
    total_steps = len(plan)

    await publisher.emit(
        task_id=task_id,
        event_type=EventType.AGENT_ACTION,
        agent_name="Researcher",
        message=f"Starting step {step_index + 1}/{total_steps}: {current_step}",
        payload={"kind": "step_started", "step_index": step_index, "step": current_step},
    )

    tool_specs = get_tool_registry()
    bound_llm = llm.bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": (spec.args_schema.__doc__ or "").strip(),
                    "parameters": spec.args_schema.model_json_schema(),
                },
            }
            for spec in tool_specs
        ]
    )

    system_prompt = RESEARCHER_SYSTEM_PROMPT.format(
        today=today,
        step_index=step_index + 1,
        total_steps=total_steps,
        current_step=current_step,
        original_prompt=state["prompt"],
        max_tool_iterations=settings.MAX_TOOL_ITERATIONS,
    )

    step_messages = [SystemMessage(content=system_prompt), HumanMessage(content=current_step)]
    tools_used: list[str] = []
    had_errors = False
    finding_text = ""

    for iteration in range(settings.MAX_TOOL_ITERATIONS + 1):
        response = await invoke_with_retry(bound_llm, step_messages, publisher, task_id)

        if hasattr(response, "content") and response.content:
            await publisher.emit(
                task_id=task_id,
                event_type=EventType.AGENT_THOUGHT,
                agent_name="Researcher",
                message=str(response.content)[:300],
                payload={"kind": "thought", "step_index": step_index, "text": response.content},
            )

        tool_calls = getattr(response, "tool_calls", []) or []

        if not tool_calls:
            finding_text = response.content if hasattr(response, "content") else str(response)
            break

        if iteration >= settings.MAX_TOOL_ITERATIONS:
            finding_text = response.content if hasattr(response, "content") else ""
            had_errors = True
            logger.warning("Researcher hit iteration cap on step %d", step_index)
            break

        step_messages.append(response)

        for tool_call in tool_calls:
            tool_name = tool_call.get("name") or tool_call.get("function", {}).get("name", "")
            tool_args = tool_call.get("args") or {}
            tool_call_id = tool_call.get("id", "")

            spec = get_spec_by_name(tool_name)
            if spec is None:
                tool_result = (
                    f"Error: Unknown tool '{tool_name}'. "
                    "Use one of: web_search, get_weather, data_calculator."
                )
                had_errors = True
            else:
                tool_result = await execute_tool(spec, tool_args, publisher, task_id)
                if tool_result.startswith("Error:"):
                    had_errors = True
                if tool_name not in tools_used:
                    tools_used.append(tool_name)

            step_messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call_id))

    compressed_finding = textwrap.shorten(finding_text, width=600, placeholder="... [truncated]")

    finding: Finding = {
        "step_index": step_index,
        "step": current_step,
        "finding": compressed_finding,
        "tools_used": tools_used,
        "had_errors": had_errors,
    }

    await publisher.emit(
        task_id=task_id,
        event_type=EventType.AGENT_THOUGHT,
        agent_name="Researcher",
        message=f"Completed step {step_index + 1}: {compressed_finding[:120]}",
        payload={"kind": "finding", **finding},
    )

    return {
        "current_step": step_index + 1,
        "findings": [finding],
        "messages": [{"agent": "Researcher", "content": compressed_finding}],
    }
