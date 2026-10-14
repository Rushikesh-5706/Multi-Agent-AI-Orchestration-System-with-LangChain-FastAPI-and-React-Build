from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.db.repositories import get_task_run, list_agent_events

logger = logging.getLogger(__name__)

router = APIRouter()

_background_tasks: set[asyncio.Task] = set()


class PromptRequest(BaseModel):
    prompt: str

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Prompt must not be empty.")
        if len(v) > 2000:
            raise ValueError("Prompt must not exceed 2000 characters.")
        return v


class TaskResponse(BaseModel):
    task_id: str


@router.post("/tasks", response_model=TaskResponse, status_code=200)
async def create_task(body: PromptRequest):
    from app.agents.runner import run_workflow
    from app.api.connection_manager import get_connection_manager
    from app.db.repositories import create_task_run

    run = await create_task_run(body.prompt)
    task_id = str(run.id)

    manager = get_connection_manager()
    task = asyncio.create_task(run_workflow(task_id, manager))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return TaskResponse(task_id=task_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError as err:
        raise HTTPException(status_code=422, detail="Invalid task_id format.") from err

    run = await get_task_run(task_uuid)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    events = await list_agent_events(task_uuid)
    events_data = [
        {
            "event_id": str(e.id),
            "sequence": e.sequence,
            "task_id": str(e.task_run_id),
            "event_type": e.event_type,
            "agent": e.agent_name,
            "payload": e.payload,
            "timestamp": e.timestamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }
        for e in events
    ]

    return {
        "id": str(run.id),
        "prompt": run.prompt,
        "status": run.status,
        "final_result": run.final_result,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "events": events_data,
    }


def get_background_tasks() -> set[asyncio.Task]:
    return _background_tasks
