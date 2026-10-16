from __future__ import annotations

import asyncio
import logging
import uuid

from app.agents.events import EventPublisher
from app.agents.graph import build_graph
from app.agents.llm import build_llm
from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.enums import EventType, TaskStatus
from app.db.repositories import set_final_result, set_task_status

logger = logging.getLogger(__name__)


async def run_workflow(task_id: str, connection_manager=None) -> None:
    settings = get_settings()
    task_uuid = uuid.UUID(task_id)

    from app.db.repositories import get_task_run

    run = await get_task_run(task_uuid)
    if run is None:
        logger.error("Task %s not found; cannot run workflow.", task_id)
        return

    publisher = EventPublisher(connection_manager)
    llm = build_llm()

    initial_state: AgentState = {
        "task_id": task_id,
        "prompt": run.prompt,
        "plan": [],
        "current_step": 0,
        "findings": [],
        "final_answer": None,
        "fatal_error": None,
    }

    graph = build_graph()
    graph_config = {
        "configurable": {
            "publisher": publisher,
            "llm": llm,
        }
    }

    try:
        await set_task_status(task_uuid, TaskStatus.IN_PROGRESS)
        final_answer = None
        fatal_error = None

        async def _stream():
            nonlocal final_answer, fatal_error
            async for chunk in graph.astream(initial_state, graph_config, stream_mode="updates"):
                for node_name, updates in chunk.items():
                    summary = _state_summary(updates)
                    await publisher.emit(
                        task_id=task_id,
                        event_type=EventType.AGENT_ACTION,
                        agent_name=node_name,
                        message=f"Node '{node_name}' completed.",
                        payload={"kind": "transition", "node": node_name, "summary": summary},
                    )
                    if "final_answer" in updates and updates["final_answer"]:
                        final_answer = updates["final_answer"]
                    if updates.get("fatal_error"):
                        fatal_error = updates["fatal_error"]
                        return

        await asyncio.wait_for(_stream(), timeout=settings.WORKFLOW_TIMEOUT_SECONDS)

        if fatal_error:
            await _fail_run(task_uuid, task_id, publisher, fatal_error)
            return

        if final_answer:
            await set_final_result(task_uuid, final_answer)
            await set_task_status(task_uuid, TaskStatus.COMPLETED)
            await publisher.emit(
                task_id=task_id,
                event_type=EventType.COMPLETED,
                agent_name="system",
                message=final_answer,
                payload={"final_result": final_answer},
            )
        else:
            await set_task_status(task_uuid, TaskStatus.FAILED)
            await publisher.emit(
                task_id=task_id,
                event_type=EventType.ERROR,
                agent_name="system",
                message="Workflow ended without producing a final answer.",
                payload={"fatal": True},
            )

    except TimeoutError:
        msg = f"Workflow timed out after {settings.WORKFLOW_TIMEOUT_SECONDS}s."
        logger.error("Workflow timeout for task %s", task_id)
        await _fail_run(task_uuid, task_id, publisher, msg)

    except asyncio.CancelledError:
        logger.warning("Workflow cancelled for task %s", task_id)
        await _fail_run(task_uuid, task_id, publisher, "Workflow was cancelled.")

    except Exception as exc:
        msg = f"Unexpected workflow error: {exc}"
        logger.exception("Unexpected error in workflow for task %s", task_id)
        await _fail_run(task_uuid, task_id, publisher, msg)


async def _fail_run(
    task_uuid: uuid.UUID, task_id: str, publisher: EventPublisher, message: str
) -> None:
    try:
        await set_task_status(task_uuid, TaskStatus.FAILED)
        await publisher.emit(
            task_id=task_id,
            event_type=EventType.ERROR,
            agent_name="system",
            message=message,
            payload={"fatal": True, "detail": message},
        )
    except Exception as exc:
        logger.error("Failed to record run failure for task %s: %s", task_id, exc)


def _state_summary(updates: dict) -> str:
    parts = []
    if "plan" in updates and updates["plan"]:
        parts.append(f"plan={updates['plan'][:2]}")
    if "current_step" in updates:
        parts.append(f"step={updates['current_step']}")
    if "final_answer" in updates and updates["final_answer"]:
        parts.append("final_answer=set")
    return ", ".join(parts) if parts else "no state changes"
