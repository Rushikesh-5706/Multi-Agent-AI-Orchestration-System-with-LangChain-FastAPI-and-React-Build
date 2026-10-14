from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.connection_manager import _Connection, get_connection_manager
from app.core.config import get_settings
from app.core.enums import EventType
from app.db.repositories import get_task_run

logger = logging.getLogger(__name__)

router = APIRouter()

_TERMINAL_EVENT_TYPES = {EventType.COMPLETED.value, EventType.ERROR.value}


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    settings = get_settings()

    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        await websocket.accept()
        await websocket.close(code=4404)
        return

    run = await get_task_run(task_uuid)
    if run is None:
        await websocket.accept()
        await websocket.close(code=4404)
        return

    await websocket.accept()
    manager = get_connection_manager()
    conn = _Connection(websocket, task_id)
    manager.register(task_id, conn)

    already_finished = False

    try:
        await manager.replay_and_stream(task_id, conn, task_uuid)

        from app.db.repositories import list_agent_events

        replayed = await list_agent_events(task_uuid, after_sequence=0)
        for event in replayed:
            if event.event_type == EventType.COMPLETED.value:
                already_finished = True
                break
            if event.event_type == EventType.ERROR.value and event.payload.get("fatal"):
                already_finished = True
                break

        if already_finished:
            await websocket.close(code=1000)
            return

        heartbeat_interval = settings.WS_HEARTBEAT_SECONDS
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=heartbeat_interval)
            except TimeoutError:
                heartbeat = {
                    "event_type": "HEARTBEAT",
                    "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                }
                try:
                    await websocket.send_json(heartbeat)
                except Exception:
                    break
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error for task %s: %s", task_id, exc)
    finally:
        manager.remove(task_id, conn)
