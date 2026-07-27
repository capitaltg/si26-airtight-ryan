"""add audio columns to turns

Revision ID: 0005_turn_audio
Revises: 0004_cache_normalized_answer
Create Date: 2026-07-27

Voice turns submit a recording instead of typed text; the transcript is what
actually gets scored (it flows into the existing extraction/scoring path
unchanged), so if a presenter disputes a number, the only way to check it is
to go back to what they actually said. These columns hold that evidence on
the turn row: the raw uploaded bytes, their content type, and the transcript
text. The content type is stored per-row rather than assumed because Chrome
records WebM and Safari records MP4, and replay has to serve back whichever
one was actually uploaded. All three are nullable — a typed turn (the
existing ``/answer`` path) never populates them.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_turn_audio"
down_revision: str | None = "0004_cache_normalized_answer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("turns", sa.Column("answer_audio", sa.LargeBinary(), nullable=True))
    op.add_column(
        "turns", sa.Column("answer_audio_content_type", sa.String(length=64), nullable=True)
    )
    op.add_column("turns", sa.Column("transcript", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("turns", "transcript")
    op.drop_column("turns", "answer_audio_content_type")
    op.drop_column("turns", "answer_audio")
