from __future__ import annotations

import logging
import uuid
from datetime import UTC

from app.core.enums import EventType
from app.db.repositories import add_agent_event

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self, connection_manager=None):
        self._manager = connection_manager

    async def emit(
        self,
        task_id: str,
        event_type: EventType,
        agent_name: str,
        message: str,
        payload: dict,
    ) -> None:
        task_uuid = uuid.UUID(task_id)
        full_payload = dict(payload)
        if "message" not in full_payload:
            full_payload["message"] = message

        try:
            event = await add_agent_event(
                task_id=task_uuid,
                agent_name=agent_name,
                event_type=event_type,
                payload=full_payload,
            )
        except Exception as exc:
            logger.error(
                "Failed to persist event %s for task %s: %s",
                event_type.value,
                task_id,
                exc,
            )
            raise

        if self._manager is not None:
            wire = {
                "event_id": str(event.id),
                "sequence": event.sequence,
                "task_id": task_id,
                "event_type": event_type.value,
                "agent": agent_name,
                "message": message,
                "payload": full_payload,
                "timestamp": event.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
                + "Z",
            }
            try:
                await self._manager.broadcast(task_id, wire)
            except Exception as exc:
                logger.warning(
                    "Failed to broadcast event to WebSocket for task %s: %s", task_id, exc
                )
