from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app.core.enums import EventType, TaskStatus
from app.db.base import Base
from app.db.repositories import add_agent_event, create_task_run, get_task_run, set_task_status
from app.db.session import dispose_engine, get_engine
from app.main import app


@pytest.fixture(autouse=True)
async def setup_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("WS_HEARTBEAT_SECONDS", "1")

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
async def test_post_task_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty prompt
        resp = await client.post("/api/tasks", json={"prompt": ""})
        assert resp.status_code == 422

        # Whitespace prompt
        resp = await client.post("/api/tasks", json={"prompt": "   "})
        assert resp.status_code == 422

        # Too long prompt (> 2000 chars)
        resp = await client.post("/api/tasks", json={"prompt": "a" * 2001})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_task_success():
    from unittest.mock import AsyncMock, patch

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.agents.runner.run_workflow", new_callable=AsyncMock):
            resp = await client.post("/api/tasks", json={"prompt": "Valid test prompt"})
            assert resp.status_code == 200
            data = resp.json()
            assert "task_id" in data
            task_uuid = uuid.UUID(data["task_id"])
            run = await get_task_run(task_uuid)
            assert run is not None
            assert run.prompt == "Valid test prompt"


@pytest.mark.asyncio
async def test_get_task_not_found_and_invalid_uuid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid UUID format
        resp = await client.get("/api/tasks/not-a-uuid")
        assert resp.status_code == 422

        # Nonexistent task
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/tasks/{fake_id}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_task_success():
    run = await create_task_run("Get task audit test")
    await add_agent_event(
        task_id=run.id,
        agent_name="Planner",
        event_type=EventType.AGENT_THOUGHT,
        payload={"message": "Formulating steps"},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{run.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(run.id)
        assert data["prompt"] == "Get task audit test"
        assert len(data["events"]) == 1
        assert data["events"][0]["agent"] == "Planner"


def test_websocket_unknown_id():
    from starlette.websockets import WebSocketDisconnect

    client = TestClient(app)
    fake_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/ws/{fake_id}") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4404


def test_websocket_replay_and_close():
    # Setup completed task in DB
    async def create_completed():
        run = await create_task_run("WS replay test")
        await add_agent_event(
            task_id=run.id,
            agent_name="Planner",
            event_type=EventType.AGENT_THOUGHT,
            payload={"message": "Planning..."},
        )
        await add_agent_event(
            task_id=run.id,
            agent_name="Synthesizer",
            event_type=EventType.COMPLETED,
            payload={"message": "All done", "final_result": "Answer 42"},
        )
        await set_task_status(run.id, TaskStatus.COMPLETED)
        return run

    run = asyncio.run(create_completed())

    client = TestClient(app)
    with client.websocket_connect(f"/api/ws/{run.id}") as ws:
        msg1 = ws.receive_json()
        assert msg1["agent"] == "Planner"
        assert msg1["sequence"] == 1

        msg2 = ws.receive_json()
        assert msg2["agent"] == "Synthesizer"
        assert msg2["event_type"] == "COMPLETED"
        assert msg2["payload"]["final_result"] == "Answer 42"


@pytest.mark.asyncio
async def test_cors_preflight_and_unlisted_origin():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Allowed origin
        resp = await client.options(
            "/api/tasks",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

        # Unlisted origin
        resp_unlisted = await client.options(
            "/api/tasks",
            headers={
                "Origin": "http://malicious-site.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert "access-control-allow-origin" not in resp_unlisted.headers
