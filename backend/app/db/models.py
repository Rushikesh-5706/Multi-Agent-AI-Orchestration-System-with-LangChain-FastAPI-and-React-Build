from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, default="PENDING")
    final_result: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    events: Mapped[list[AgentEvent]] = relationship(
        "AgentEvent",
        back_populates="task_run",
        order_by="AgentEvent.sequence",
        cascade="all, delete-orphan",
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    task_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        sa.ForeignKey("task_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    agent_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(
        sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_utcnow
    )

    task_run: Mapped[TaskRun] = relationship("TaskRun", back_populates="events")

    __table_args__ = (
        sa.UniqueConstraint("task_run_id", "sequence", name="uq_task_event_sequence"),
    )
