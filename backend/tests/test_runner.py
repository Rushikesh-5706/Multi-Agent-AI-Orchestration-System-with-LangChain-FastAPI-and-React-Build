from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.runner import run_workflow
from app.core.config import get_settings
from app.core.enums import EventType, TaskStatus
from app.db.repositories import create_task_run, get_task_run, list_agent_events


@pytest.mark.asyncio
async def test_workflow_status_moves_to_completed_with_transitions() -> None:
    run = await create_task_run("Status transition test")
    assert run.status == TaskStatus.PENDING.value

    # Mock graph to return final answer
    async def fake_astream(*args, **kwargs):
        yield {"planner": {"plan": ["Step 1"], "current_step": 0}}
        yield {"researcher": {"current_step": 1, "findings": []}}
        yield {"synthesizer": {"final_answer": "Complete result answer"}}

    mock_graph = AsyncMock()
    mock_graph.astream = fake_astream

    with patch("app.agents.runner.build_graph", return_value=mock_graph):
        with patch("app.agents.runner.build_llm"):
            await run_workflow(str(run.id))

    updated_run = await get_task_run(run.id)
    assert updated_run is not None
    assert updated_run.status == TaskStatus.COMPLETED.value
    assert updated_run.final_result == "Complete result answer"

    # Verify transitions recorded
    events = await list_agent_events(run.id)
    transition_events = [e for e in events if e.payload.get("kind") == "transition"]
    assert len(transition_events) == 3
    nodes = [e.payload.get("node") for e in transition_events]
    assert nodes == ["planner", "researcher", "synthesizer"]


@pytest.mark.asyncio
async def test_workflow_timeout_ends_failed() -> None:
    run = await create_task_run("Timeout test")

    async def fake_slow_stream(*args, **kwargs):
        await asyncio.sleep(10)
        yield {"synthesizer": {"final_answer": "Too late"}}

    mock_graph = AsyncMock()
    mock_graph.astream = fake_slow_stream

    with patch("app.agents.runner.build_graph", return_value=mock_graph):
        with patch("app.agents.runner.build_llm"):
            with patch.object(get_settings(), "WORKFLOW_TIMEOUT_SECONDS", 0.05):
                await run_workflow(str(run.id))

    updated_run = await get_task_run(run.id)
    assert updated_run is not None
    assert updated_run.status == TaskStatus.FAILED.value

    events = await list_agent_events(run.id)
    error_events = [e for e in events if e.event_type == EventType.ERROR.value]
    assert any("timed out" in e.payload.get("message", "").lower() for e in error_events)


@pytest.mark.asyncio
async def test_workflow_cancellation_ends_failed() -> None:
    run = await create_task_run("Cancellation test")

    async def fake_cancelling_stream(*args, **kwargs):
        raise asyncio.CancelledError()
        yield {}

    mock_graph = AsyncMock()
    mock_graph.astream = fake_cancelling_stream

    with patch("app.agents.runner.build_graph", return_value=mock_graph):
        with patch("app.agents.runner.build_llm"):
            await run_workflow(str(run.id))

    updated_run = await get_task_run(run.id)
    assert updated_run is not None
    assert updated_run.status == TaskStatus.FAILED.value

    events = await list_agent_events(run.id)
    error_events = [e for e in events if e.event_type == EventType.ERROR.value]
    assert any("cancelled" in e.payload.get("message", "").lower() for e in error_events)


@pytest.mark.asyncio
async def test_workflow_missing_final_answer_ends_failed() -> None:
    run = await create_task_run("Missing answer test")

    async def fake_empty_stream(*args, **kwargs):
        yield {"planner": {"plan": ["Step 1"]}}
        yield {"researcher": {"current_step": 1}}
        yield {"synthesizer": {}}  # No final_answer

    mock_graph = AsyncMock()
    mock_graph.astream = fake_empty_stream

    with patch("app.agents.runner.build_graph", return_value=mock_graph):
        with patch("app.agents.runner.build_llm"):
            await run_workflow(str(run.id))

    updated_run = await get_task_run(run.id)
    assert updated_run is not None
    assert updated_run.status == TaskStatus.FAILED.value

    events = await list_agent_events(run.id)
    error_events = [e for e in events if e.event_type == EventType.ERROR.value]
    assert any(
        "without producing a final answer" in e.payload.get("message", "") for e in error_events
    )
