from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC

from app.core.enums import EventType

logger = logging.getLogger(__name__)

_TERMINAL_EVENT_TYPES = {EventType.COMPLETED.value, EventType.ERROR.value}


class _Connection:
    def __init__(self, ws, task_id: str):
        self.ws = ws
        self.task_id = task_id
        self.last_sequence: int = 0
        self._lock = asyncio.Lock()

    async def send(self, data: dict) -> bool:
        async with self._lock:
            try:
                await self.ws.send_json(data)
                event_type = data.get("event_type")
                is_fatal_error = event_type == "ERROR" and data.get("payload", {}).get("fatal")
                if event_type == "COMPLETED" or is_fatal_error:
                    try:
                        await self.ws.close(code=1000)
                    except Exception:
                        pass
                    return False
                return True
            except Exception as exc:
                logger.debug("WebSocket send failed for task %s: %s", self.task_id, exc)
                return False


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[_Connection]] = defaultdict(set)

    def register(self, task_id: str, conn: _Connection) -> None:
        self._connections[task_id].add(conn)

    def remove(self, task_id: str, conn: _Connection) -> None:
        self._connections[task_id].discard(conn)
        if not self._connections[task_id]:
            del self._connections[task_id]

    async def broadcast(self, task_id: str, message: dict) -> None:
        seq = message.get("sequence", 0)
        dead: list[_Connection] = []

        for conn in list(self._connections.get(task_id, set())):
            if seq <= conn.last_sequence:
                continue
            ok = await conn.send(message)
            if ok:
                conn.last_sequence = seq
            else:
                dead.append(conn)

        for conn in dead:
            self.remove(task_id, conn)

    async def replay_and_stream(self, task_id: str, conn: _Connection, task_uuid) -> bool:
        """Replay persisted events to the connection while holding its send lock.

        Returns True if a terminal event (COMPLETED or fatal ERROR) was among
        the replayed events, meaning the caller should close the socket.
        """
        from app.db.repositories import list_agent_events

        terminal_found = False

        async with conn._lock:
            events = await list_agent_events(task_uuid, after_sequence=0)

            for event in events:
                wire = {
                    "event_id": str(event.id),
                    "sequence": event.sequence,
                    "task_id": task_id,
                    "event_type": event.event_type,
                    "agent": event.agent_name,
                    "message": event.payload.get("message", ""),
                    "payload": event.payload,
                    "timestamp": event.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[
                        :-3
                    ]
                    + "Z",
                }
                await conn.ws.send_json(wire)
                conn.last_sequence = event.sequence

                if event.event_type == EventType.COMPLETED.value:
                    terminal_found = True
                elif event.event_type == EventType.ERROR.value and event.payload.get("fatal"):
                    terminal_found = True

        return terminal_found


_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
