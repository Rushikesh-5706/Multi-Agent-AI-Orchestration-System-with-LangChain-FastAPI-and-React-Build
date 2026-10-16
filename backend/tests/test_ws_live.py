from __future__ import annotations

import asyncio
import uuid

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.connection_manager import get_connection_manager
from app.core.enums import EventType, TaskStatus
from app.db.repositories import add_agent_event, create_task_run, set_task_status
from app.main import app


def test_ws_invalid_uuid_and_unknown_id_give_4404() -> None:
    client = TestClient(app)

    # Invalid UUID
    with client.websocket_connect("/api/ws/not-a-uuid") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4404

    # Unknown ID
    fake_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/ws/{fake_id}") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4404


def test_ws_connecting_after_completion_replays_and_closes() -> None:
    async def create_completed_task():
        run = await create_task_run("Completed task replay")
        await add_agent_event(
            task_id=run.id,
            agent_name="Planner",
            event_type=EventType.AGENT_THOUGHT,
            payload={"message": "Done planning"},
        )
        await add_agent_event(
            task_id=run.id,
            agent_name="system",
            event_type=EventType.COMPLETED,
            payload={"message": "All done", "final_result": "Final answer"},
        )
        await set_task_status(run.id, TaskStatus.COMPLETED)
        return run

    run = asyncio.run(create_completed_task())
    client = TestClient(app)

    with client.websocket_connect(f"/api/ws/{run.id}") as ws:
        msg1 = ws.receive_json()
        assert msg1["sequence"] == 1
        msg2 = ws.receive_json()
        assert msg2["sequence"] == 2
        assert msg2["event_type"] == "COMPLETED"
        # Socket should close with 1000
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1000


def test_ws_mid_run_and_two_clients() -> None:
    async def create_in_progress_task():
        run = await create_task_run("Mid-run two clients")
        await add_agent_event(
            task_id=run.id,
            agent_name="Planner",
            event_type=EventType.AGENT_THOUGHT,
            payload={"message": "Event 1"},
        )
        return run

    run = asyncio.run(create_in_progress_task())
    manager = get_connection_manager()
    client = TestClient(app)

    with client.websocket_connect(f"/api/ws/{run.id}") as ws1:
        with client.websocket_connect(f"/api/ws/{run.id}") as ws2:
            # Both receive replayed event 1
            m1_1 = ws1.receive_json()
            m2_1 = ws2.receive_json()
            assert m1_1["sequence"] == 1
            assert m2_1["sequence"] == 1

            # Broadcast live event 2
            live_event = {
                "event_id": str(uuid.uuid4()),
                "sequence": 2,
                "task_id": str(run.id),
                "event_type": "AGENT_ACTION",
                "agent": "Researcher",
                "message": "Step 1",
                "payload": {"message": "Step 1"},
                "timestamp": "2026-10-16T12:00:00.000Z",
            }
            asyncio.run(manager.broadcast(str(run.id), live_event))

            m1_2 = ws1.receive_json()
            m2_2 = ws2.receive_json()
            assert m1_2["sequence"] == 2
            assert m2_2["sequence"] == 2

            # Broadcast terminal COMPLETED event
            terminal_event = {
                "event_id": str(uuid.uuid4()),
                "sequence": 3,
                "task_id": str(run.id),
                "event_type": "COMPLETED",
                "agent": "system",
                "message": "Done",
                "payload": {"final_result": "Success"},
                "timestamp": "2026-10-16T12:00:01.000Z",
            }
            asyncio.run(manager.broadcast(str(run.id), terminal_event))

            m1_3 = ws1.receive_json()
            m2_3 = ws2.receive_json()
            assert m1_3["sequence"] == 3
            assert m2_3["sequence"] == 3

            # Both close with code 1000
            with pytest.raises(WebSocketDisconnect) as exc1:
                ws1.receive_json()
            assert exc1.value.code == 1000

            with pytest.raises(WebSocketDisconnect) as exc2:
                ws2.receive_json()
            assert exc2.value.code == 1000
