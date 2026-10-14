from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.events import EventPublisher
from app.agents.llm import invoke_with_retry
from app.agents.prompts import SYNTHESIZER_SYSTEM_PROMPT
from app.agents.state import AgentState
from app.core.enums import EventType

logger = logging.getLogger(__name__)


async def synthesizer_node(state: AgentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {})
    publisher: EventPublisher = configurable["publisher"]
    llm = configurable["llm"]
    task_id = state["task_id"]

    await publisher.emit(
        task_id=task_id,
        event_type=EventType.AGENT_ACTION,
        agent_name="Synthesizer",
        message="Synthesizing findings into final answer.",
        payload={"kind": "synthesis_started"},
    )

    plan_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(state["plan"]))
    findings_text = "\n\n".join(
        f"Step {f['step_index'] + 1} ({f['step']}):\n{f['finding']}"
        + ("\n[Note: tool errors occurred during this step]" if f.get("had_errors") else "")
        for f in state["findings"]
    )

    system_prompt = SYNTHESIZER_SYSTEM_PROMPT.format(
        original_prompt=state["prompt"],
        plan_text=plan_text,
        findings_text=findings_text,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="Please synthesize the findings into a final answer now."),
    ]

    response = await invoke_with_retry(llm, messages, publisher, task_id)
    final_answer = response.content if hasattr(response, "content") else str(response)

    return {
        "final_answer": final_answer,
        "messages": [{"agent": "Synthesizer", "content": final_answer}],
    }
