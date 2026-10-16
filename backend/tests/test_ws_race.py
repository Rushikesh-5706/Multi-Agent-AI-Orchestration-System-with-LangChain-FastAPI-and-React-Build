from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.api.connection_manager import ConnectionManager, _Connection
from app.db.models import AgentEvent


@pytest.mark.asyncio
async def test_websocket_replay_broadcast_race_prevents_duplicate_delivery() -> None:
    manager = ConnectionManager()
    task_id = str(uuid.uuid4())
    task_uuid = uuid.UUID(task_id)

    received_messages: list[dict] = []
    fake_ws = AsyncMock()

    async def fake_send_json(data: dict) -> None:
        received_messages.append(data)

    fake_ws.send_json = fake_send_json
    fake_ws.close = AsyncMock()

    conn = _Connection(fake_ws, task_id)
    manager.register(task_id, conn)

    mock_event = AgentEvent(
        id=uuid.uuid4(),
        task_run_id=task_uuid,
        sequence=1,
        agent_name="Researcher",
        event_type="AGENT_ACTION",
        payload={"message": "Step 1 started"},
        timestamp=datetime.now(UTC),
    )

    replay_started = asyncio.Event()
    replay_release = asyncio.Event()

    async def mock_list_agent_events(_task_uuid, after_sequence=0):
        replay_started.set()
        await replay_release.wait()
        return [mock_event]

    # Replay task
    async def run_replay():
        return await manager.replay_and_stream(task_id, conn, task_uuid)

    from unittest.mock import patch

    with patch("app.db.repositories.list_agent_events", side_effect=mock_list_agent_events):
        replay_task = asyncio.create_task(run_replay())

        # Wait until replay has acquired the lock and called list_agent_events
        await replay_started.wait()

        # Concurrently attempt to broadcast sequence 1
        broadcast_task = asyncio.create_task(
            manager.broadcast(
                task_id,
                {
                    "event_id": str(mock_event.id),
                    "sequence": 1,
                    "task_id": task_id,
                    "event_type": "AGENT_ACTION",
                    "agent": "Researcher",
                    "message": "Step 1 started",
                    "payload": {"message": "Step 1 started"},
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                },
            )
        )

        # Release replay to finish sending sequence 1
        replay_release.set()

        await asyncio.gather(replay_task, broadcast_task)

    # Sequence 1 must be received exactly once
    sequences = [msg.get("sequence") for msg in received_messages]
    assert sequences == [1], f"Expected exactly [1], got {sequences}"
