from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.connection_manager import _Connection, get_connection_manager
from app.core.config import get_settings
from app.db.repositories import get_task_run

logger = logging.getLogger(__name__)

router = APIRouter()


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

    # Register before replay so live broadcasts during replay are queued behind
    # the per-connection lock. After replay the lock is released and broadcasts
    # deliver only events whose sequence exceeds last_sequence, preventing dupes.
    manager.register(task_id, conn)

    already_finished = False

    try:
        already_finished = await manager.replay_and_stream(task_id, conn, task_uuid)

        if already_finished:
            try:
                await websocket.close(code=1000)
            except Exception:
                pass
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
