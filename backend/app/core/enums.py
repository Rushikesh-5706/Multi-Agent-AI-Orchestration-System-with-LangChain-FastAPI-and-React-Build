from __future__ import annotations

import enum


class TaskStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EventType(enum.StrEnum):
    AGENT_THOUGHT = "AGENT_THOUGHT"
    AGENT_ACTION = "AGENT_ACTION"
    TOOL_INVOCATION = "TOOL_INVOCATION"
    TOOL_RESULT = "TOOL_RESULT"
    ERROR = "ERROR"
    COMPLETED = "COMPLETED"
