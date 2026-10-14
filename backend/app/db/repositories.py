from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventType, TaskStatus
from app.db.models import AgentEvent, TaskRun
from app.db.session import get_sessionmaker


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def create_task_run(prompt: str) -> TaskRun:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        run = TaskRun(
            id=uuid.uuid4(),
            prompt=prompt,
            status=TaskStatus.PENDING.value,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def get_task_run(task_id: uuid.UUID) -> TaskRun | None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.get(TaskRun, task_id)
        return result


async def set_task_status(
    task_id: uuid.UUID,
    status: TaskStatus,
    session: AsyncSession | None = None,
) -> None:
    terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED}
    now = _utcnow()
    values: dict = {"status": status.value, "updated_at": now}
    if status in terminal:
        values["completed_at"] = now

    if session is not None:
        await session.execute(update(TaskRun).where(TaskRun.id == task_id).values(**values))
    else:
        session_factory = get_sessionmaker()
        async with session_factory() as sess:
            await sess.execute(update(TaskRun).where(TaskRun.id == task_id).values(**values))
            await sess.commit()


async def set_final_result(task_id: uuid.UUID, result: str) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await session.execute(
            update(TaskRun)
            .where(TaskRun.id == task_id)
            .values(final_result=result, updated_at=_utcnow())
        )
        await session.commit()


async def add_agent_event(
    task_id: uuid.UUID,
    agent_name: str,
    event_type: EventType,
    payload: dict,
    session: AsyncSession | None = None,
) -> AgentEvent:
    async def _insert(sess: AsyncSession) -> AgentEvent:
        next_seq_result = await sess.execute(
            select(func.coalesce(func.max(AgentEvent.sequence), 0) + 1).where(
                AgentEvent.task_run_id == task_id
            )
        )
        next_seq: int = next_seq_result.scalar_one()

        event = AgentEvent(
            id=uuid.uuid4(),
            task_run_id=task_id,
            sequence=next_seq,
            agent_name=agent_name,
            event_type=event_type.value,
            payload=payload,
            timestamp=_utcnow(),
        )
        sess.add(event)
        await sess.flush()
        await sess.refresh(event)
        return event

    if session is not None:
        return await _insert(session)

    session_factory = get_sessionmaker()
    async with session_factory() as sess:
        event = await _insert(sess)
        await sess.commit()
        return event


async def list_agent_events(task_id: uuid.UUID, after_sequence: int = 0) -> list[AgentEvent]:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(
            select(AgentEvent)
            .where(
                AgentEvent.task_run_id == task_id,
                AgentEvent.sequence > after_sequence,
            )
            .order_by(AgentEvent.sequence)
        )
        return list(result.scalars().all())


async def mark_interrupted_runs_failed() -> int:
    from app.core.enums import EventType

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(
            select(TaskRun).where(
                TaskRun.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value])
            )
        )
        runs = result.scalars().all()
        count = 0
        for run in runs:
            run.status = TaskStatus.FAILED.value
            now = _utcnow()
            run.updated_at = now
            run.completed_at = now

            next_seq_result = await session.execute(
                select(func.coalesce(func.max(AgentEvent.sequence), 0) + 1).where(
                    AgentEvent.task_run_id == run.id
                )
            )
            next_seq: int = next_seq_result.scalar_one()

            event = AgentEvent(
                id=uuid.uuid4(),
                task_run_id=run.id,
                sequence=next_seq,
                agent_name="system",
                event_type=EventType.ERROR.value,
                payload={
                    "message": "Run interrupted by a service restart",
                    "fatal": True,
                },
                timestamp=now,
            )
            session.add(event)
            count += 1

        await session.commit()
        return count
