from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.agents.nodes.planner import _parse_plan
from app.agents.runner import run_workflow
from app.core.enums import EventType, TaskStatus
from app.db.base import Base
from app.db.repositories import create_task_run, get_task_run, list_agent_events
from app.db.session import dispose_engine, get_engine


@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_agents.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
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


def test_parse_plan_json_array():
    content = 'Here is the plan:\n["Search Tokyo weather", "Calculate temperature diff"]'
    plan = _parse_plan(content, max_steps=5)
    assert plan == ["Search Tokyo weather", "Calculate temperature diff"]


def test_parse_plan_json_object():
    content = '{"steps": ["Check weather", "Check packing guidelines"]}'
    plan = _parse_plan(content, max_steps=5)
    assert plan == ["Check weather", "Check packing guidelines"]


def test_parse_plan_invalid():
    assert _parse_plan("No json here at all", max_steps=5) is None


@pytest.mark.asyncio
async def test_end_to_end_mocked_graph():
    # Create scripted LLM
    mock_llm = MagicMock()

    # Step 1: Planner outputs plan
    planner_response = AIMessage(content='["Get weather in Tokyo", "Summarize clothing advice"]')
    # Step 2: Researcher step 1 invokes get_weather
    researcher_call = AIMessage(
        content="I will check the weather.",
        tool_calls=[
            {
                "name": "data_calculator",
                "args": {"operation": "expression", "expression": "20 + 2"},
                "id": "call_1",
            }
        ],
    )
    researcher_done1 = AIMessage(content="Calculation indicates 22 degrees.")
    # Step 3: Researcher step 2
    researcher_done2 = AIMessage(content="Pack light jacket and comfortable shoes.")
    # Step 4: Synthesizer response
    synthesizer_response = AIMessage(
        content="The temperature is 22C in Tokyo. You should pack a light jacket."
    )

    responses = [
        planner_response,
        researcher_call,
        researcher_done1,
        researcher_done2,
        synthesizer_response,
    ]

    async def fake_ainvoke(*args, **kwargs):
        if responses:
            return responses.pop(0)
        return AIMessage(content="Finished")

    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    task_run = await create_task_run("What to pack for Tokyo?")
    task_id = str(task_run.id)

    with patch("app.agents.runner.build_llm", return_value=mock_llm):
        await run_workflow(task_id)

    updated_run = await get_task_run(task_run.id)
    assert updated_run is not None
    assert updated_run.status == TaskStatus.COMPLETED.value
    assert updated_run.final_result is not None
    assert "The temperature is 22C in Tokyo" in updated_run.final_result

    events = await list_agent_events(task_run.id)
    event_types = [e.event_type for e in events]
    assert EventType.AGENT_ACTION.value in event_types
    assert EventType.TOOL_INVOCATION.value in event_types
    assert EventType.TOOL_RESULT.value in event_types
    assert EventType.COMPLETED.value in event_types
