"""add the extraction pin table

Revision ID: 0007_extraction_pin
Revises: 0006_session_history
Create Date: 2026-07-31

Pins one extraction per turn-input so a rerun of the same answer scores the same
number. Separate from ``model_response_cache``, which keys on the rendered prompt
and self-invalidates on any content or wording change; this table keys on the
inputs themselves. Cross-session by design, so no FK to ``sessions``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_extraction_pin"
down_revision: str | None = "0006_session_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_pin",
        sa.Column("input_hash", sa.String(length=64), primary_key=True),
        sa.Column(
            "tool_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("extraction_pin")
