"""add the extractor contract version and turn extraction provenance

Revision ID: 0008_extractor_contract_version
Revises: 0007_extraction_pin
Create Date: 2026-08-05

The extraction pin key now includes the model id and the extractor contract
version, so a model upgrade or a prompt-semantics fix invalidates the pin instead
of silently replaying a pre-fix extraction. Turns record which path produced their
extraction.

IRREVERSIBLE: the upgrade deletes every existing ``extraction_pin`` row. The
downgrade drops the columns; it cannot bring the rows back.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_extractor_contract_version"
down_revision: str | None = "0007_extraction_pin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows are unreachable under the new key: their inputs are not
    # stored, so their hashes cannot be recomputed. Clear them rather than leave
    # rows nothing can ever read. The table is a replay cache, not a system of
    # record — the cost is re-extraction, not lost data.
    op.execute(sa.text("DELETE FROM extraction_pin"))
    op.add_column(
        "extraction_pin",
        sa.Column("extractor_contract_version", sa.Integer(), nullable=False),
    )
    op.add_column(
        "turns",
        sa.Column(
            "extraction_provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("turns", "extraction_provenance")
    op.drop_column("extraction_pin", "extractor_contract_version")
