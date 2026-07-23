"""add clarifications table

Revision ID: 0002_clarifications
Revises: 0001_init
Create Date: 2026-07-23

A clarification is a non-scored turn type: the evaluator answers a clarifying
question without extraction, scoring, meter change, ledger append, or agenda
advance. It lives in its own table (never ``turns``) so it cannot count as an
attempt or advance the agenda by construction.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_clarifications"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clarifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("concern_id", sa.String(length=64), nullable=False),
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clarifications_session_id", "clarifications", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_clarifications_session_id", table_name="clarifications")
    op.drop_table("clarifications")
