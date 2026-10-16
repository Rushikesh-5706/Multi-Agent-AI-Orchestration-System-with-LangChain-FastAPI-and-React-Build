from __future__ import annotations

from datetime import UTC
from typing import Any


def serialize_event(event: Any) -> dict[str, Any]:
    event_id = str(
        getattr(event, "id", None) or (event.get("id") if isinstance(event, dict) else "")
    )
    sequence = getattr(event, "sequence", None)
    if sequence is None and isinstance(event, dict):
        sequence = event.get("sequence", 0)

    task_id = getattr(event, "task_run_id", None) or getattr(event, "task_id", None)
    if task_id is None and isinstance(event, dict):
        task_id = event.get("task_id") or event.get("task_run_id", "")
    task_id_str = str(task_id)

    event_type = getattr(event, "event_type", None)
    if event_type is None and isinstance(event, dict):
        event_type = event.get("event_type", "")
    if hasattr(event_type, "value"):
        event_type_str = event_type.value
    else:
        event_type_str = str(event_type)

    agent = getattr(event, "agent_name", None) or getattr(event, "agent", None)
    if agent is None and isinstance(event, dict):
        agent = event.get("agent_name") or event.get("agent", "")

    payload = getattr(event, "payload", None)
    if payload is None and isinstance(event, dict):
        payload = event.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    message = payload.get("message", "")

    timestamp = getattr(event, "timestamp", None)
    if timestamp is None and isinstance(event, dict):
        timestamp = event.get("timestamp")

    if timestamp is not None and hasattr(timestamp, "astimezone"):
        ts_str = timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    elif isinstance(timestamp, str):
        ts_str = timestamp
    else:
        ts_str = ""

    return {
        "event_id": event_id,
        "sequence": sequence,
        "task_id": task_id_str,
        "event_type": event_type_str,
        "agent": agent,
        "message": message,
        "payload": payload,
        "timestamp": ts_str,
    }
