"""init runtime state tables

Revision ID: 0001_init
Revises:
Create Date: 2026-07-20

Creates the runtime session/audit tables. Authored content is never stored in
the DB, so nothing here mirrors the RFP/personas/concerns/rubric.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_version", sa.String(length=64), nullable=False),
        sa.Column("rubric_version", sa.Integer(), nullable=False),
        sa.Column("persona_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column("concern_id", sa.String(length=64), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("extraction_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reaction_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])
    op.create_table(
        "claim_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("backing", sa.String(length=32), nullable=True),
        sa.Column("span", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claim_ledger_session_id", "claim_ledger", ["session_id"])
    op.create_table(
        "persona_meters",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column("support", sa.Integer(), nullable=False),
        sa.Column("capped", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "persona_id"),
    )
    op.create_table(
        "concern_status",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("concern_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "concern_id"),
    )


def downgrade() -> None:
    op.drop_table("concern_status")
    op.drop_table("persona_meters")
    op.drop_index("ix_claim_ledger_session_id", table_name="claim_ledger")
    op.drop_table("claim_ledger")
    op.drop_index("ix_turns_session_id", table_name="turns")
    op.drop_table("turns")
    op.drop_table("sessions")
