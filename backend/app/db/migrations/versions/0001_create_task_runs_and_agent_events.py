"""create task_runs and agent_events tables

Revision ID: 0001
Revises:
Create Date: 2026-10-14

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("final_result", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "agent_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["task_run_id"],
            ["task_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_run_id", "sequence", name="uq_task_event_sequence"),
    )
    op.create_index(
        "ix_agent_events_task_run_id",
        "agent_events",
        ["task_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_events_task_run_id", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_table("task_runs")
