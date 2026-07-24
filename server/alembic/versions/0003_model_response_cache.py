"""add model_response_cache table

Revision ID: 0003_model_response_cache
Revises: 0002_clarifications
Create Date: 2026-07-24

Pins Bedrock output for reproducible rehearsals. ``temperature=0`` is not
reproducible on Bedrock, so the first successful response for a given request
is stored keyed by a sha256 of the full request and replayed on later identical
requests. The table is intentionally standalone — not scoped to or FK'd from
``sessions`` — because reproducibility must hold across separate runs (separate
sessions), so the key is the request content alone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_model_response_cache"
down_revision: str | None = "0002_clarifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_response_cache",
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("request_hash"),
    )


def downgrade() -> None:
    op.drop_table("model_response_cache")
