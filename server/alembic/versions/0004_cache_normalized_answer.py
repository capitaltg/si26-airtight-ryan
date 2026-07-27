"""add normalized_answer column to model_response_cache

Revision ID: 0004_cache_normalized_answer
Revises: 0003_model_response_cache
Create Date: 2026-07-27

The presenter's answer is embedded in the extraction prompt's dynamic suffix,
so a whitespace- or case-only retype produced different request bytes and
missed the cache. The cache key now hashes a normalized form of that text
instead (see ``app.bedrock.cache.normalize_answer``); this column records that
normalized form on the row so a key mismatch is inspectable in the DB.
Nullable so existing rows migrate without a backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_cache_normalized_answer"
down_revision: str | None = "0003_model_response_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_response_cache",
        sa.Column("normalized_answer", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_response_cache", "normalized_answer")
