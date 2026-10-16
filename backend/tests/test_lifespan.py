from __future__ import annotations

import pytest

from app.core.enums import EventType, TaskStatus
from app.db.repositories import create_task_run, get_task_run, list_agent_events, set_task_status
from app.main import app


@pytest.mark.asyncio
async def test_lifespan_marks_interrupted_runs_failed() -> None:
    # Create a pending run and an in_progress run
    pending_run = await create_task_run("Pending run before crash")
    in_progress_run = await create_task_run("Running task before crash")
    await set_task_status(in_progress_run.id, TaskStatus.IN_PROGRESS)

    async with app.router.lifespan_context(app):
        pass

    # Verify both runs are marked FAILED
    updated_pending = await get_task_run(pending_run.id)
    assert updated_pending is not None
    assert updated_pending.status == TaskStatus.FAILED.value

    updated_in_progress = await get_task_run(in_progress_run.id)
    assert updated_in_progress is not None
    assert updated_in_progress.status == TaskStatus.FAILED.value

    # Verify interruption event was recorded
    events = await list_agent_events(in_progress_run.id)
    error_events = [e for e in events if e.event_type == EventType.ERROR.value]
    assert len(error_events) >= 1
    assert "interrupted" in error_events[0].payload.get("message", "").lower()
