from __future__ import annotations

import uuid

import pytest

from app.core.enums import EventType, TaskStatus
from app.db.base import Base
from app.db.models import TaskRun
from app.db.repositories import (
    add_agent_event,
    create_task_run,
    get_task_run,
    list_agent_events,
    mark_interrupted_runs_failed,
    set_task_status,
)
from app.db.session import dispose_engine, get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
async def setup_test_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    from app.core.config import get_settings

    get_settings.cache_clear()

    await dispose_engine()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_engine()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_create_task_run():
    prompt = "Test multi-agent prompt"
    run = await create_task_run(prompt)
    assert run.id is not None
    assert isinstance(run.id, uuid.UUID)
    assert run.prompt == prompt
    assert run.status == TaskStatus.PENDING.value
    assert run.created_at is not None
    assert run.updated_at is not None
    assert run.completed_at is None


@pytest.mark.asyncio
async def test_status_transitions_and_timestamps():
    run = await create_task_run("Status test")
    initial_updated = run.updated_at

    await set_task_status(run.id, TaskStatus.IN_PROGRESS)
    fetched = await get_task_run(run.id)
    assert fetched is not None
    assert fetched.status == TaskStatus.IN_PROGRESS.value
    assert fetched.completed_at is None
    assert fetched.updated_at >= initial_updated

    await set_task_status(run.id, TaskStatus.COMPLETED)
    completed_run = await get_task_run(run.id)
    assert completed_run is not None
    assert completed_run.status == TaskStatus.COMPLETED.value
    assert completed_run.completed_at is not None


@pytest.mark.asyncio
async def test_event_insertion_order_and_sequence():
    run = await create_task_run("Sequence test")
    e1 = await add_agent_event(
        task_id=run.id,
        agent_name="Planner",
        event_type=EventType.AGENT_THOUGHT,
        payload={"thought": "Formulating plan"},
    )
    e2 = await add_agent_event(
        task_id=run.id,
        agent_name="Researcher",
        event_type=EventType.TOOL_INVOCATION,
        payload={"tool": "web_search", "query": "python"},
    )
    e3 = await add_agent_event(
        task_id=run.id,
        agent_name="Synthesizer",
        event_type=EventType.COMPLETED,
        payload={"result": "Done"},
    )

    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e3.sequence == 3

    events = await list_agent_events(run.id)
    assert len(events) == 3
    assert [e.sequence for e in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_list_agent_events_after_sequence():
    run = await create_task_run("After sequence test")
    for i in range(1, 6):
        await add_agent_event(
            task_id=run.id,
            agent_name="Planner",
            event_type=EventType.AGENT_ACTION,
            payload={"step": i},
        )

    filtered = await list_agent_events(run.id, after_sequence=3)
    assert len(filtered) == 2
    assert [e.sequence for e in filtered] == [4, 5]


@pytest.mark.asyncio
async def test_json_payload_round_trip():
    run = await create_task_run("JSON payload test")
    complex_payload = {
        "nested": {"key": "value", "list": [1, 2, 3]},
        "flag": True,
        "count": 42,
    }
    await add_agent_event(
        task_id=run.id,
        agent_name="Researcher",
        event_type=EventType.TOOL_RESULT,
        payload=complex_payload,
    )

    events = await list_agent_events(run.id)
    assert len(events) == 1
    assert events[0].payload == complex_payload


@pytest.mark.asyncio
async def test_cascade_delete():
    run = await create_task_run("Cascade delete test")
    await add_agent_event(
        task_id=run.id,
        agent_name="Planner",
        event_type=EventType.AGENT_THOUGHT,
        payload={"text": "Step 1"},
    )

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        fetched = await session.get(TaskRun, run.id)
        assert fetched is not None
        await session.delete(fetched)
        await session.commit()

    events = await list_agent_events(run.id)
    assert len(events) == 0


@pytest.mark.asyncio
async def test_mark_interrupted_runs_failed():
    run1 = await create_task_run("Run 1")
    run2 = await create_task_run("Run 2")
    await set_task_status(run2.id, TaskStatus.IN_PROGRESS)
    run3 = await create_task_run("Run 3")
    await set_task_status(run3.id, TaskStatus.COMPLETED)

    count = await mark_interrupted_runs_failed()
    assert count == 2

    r1 = await get_task_run(run1.id)
    r2 = await get_task_run(run2.id)
    r3 = await get_task_run(run3.id)
    assert r1.status == TaskStatus.FAILED.value
    assert r2.status == TaskStatus.FAILED.value
    assert r3.status == TaskStatus.COMPLETED.value
