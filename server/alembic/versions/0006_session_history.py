"""add session history columns

Revision ID: 0006_session_history
Revises: 0005_turn_audio
Create Date: 2026-07-28

A finished rehearsal becomes history. ``sessions.archived_at`` is the flag and
the sort key; ``sessions.report_json`` holds the report snapshotted at finish so
reading history costs no model call and the archived report survives a content
or rubric version bump unchanged.

The prompt columns freeze what was actually asked. Deriving prompt text at read
time from ``concern.core_ask`` would let a content bump silently rewrite an
archived transcript, which is the opposite of an auditable record. All five
columns are nullable: rows written before this revision have no value, and the
read paths fall back to the content-derived core ask.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_session_history"
down_revision: str | None = "0005_turn_audio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("turns", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("turns", sa.Column("prompt_intro", sa.Text(), nullable=True))
    op.add_column("clarifications", sa.Column("prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clarifications", "prompt")
    op.drop_column("turns", "prompt_intro")
    op.drop_column("turns", "prompt")
    op.drop_column("sessions", "report_json")
    op.drop_column("sessions", "archived_at")
