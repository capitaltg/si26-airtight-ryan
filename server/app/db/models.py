"""SQLAlchemy 2.0 models for runtime session/audit state (task 7).

Authored content (RFP, personas, concerns, rubric) is never stored here — it
lives in version-tagged files and is rehydrated into prompts. These tables hold
only what a rehearsal produces: the session, its turns (with the verbatim
extraction/score/reaction blobs), the running claim ledger, per-persona meters,
and per-concern status.

Portable column types
---------------------
``JSON_`` is a plain JSON column that becomes native ``JSONB`` on Postgres and a
JSON-encoded text column on SQLite. That keeps the deploy on JSONB while unit
tests run offline against in-memory SQLite with the same schema. ``Uuid`` maps to
native UUID on Postgres and CHAR(32) elsewhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on Postgres, JSON-as-text on SQLite (tests). Same Python type either way.
JSON_ = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class RehearsalSession(Base):
    """One rehearsal run. Named ``RehearsalSession`` to avoid colliding with
    SQLAlchemy's ORM ``Session``; the table is ``sessions``."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_version: Mapped[str] = mapped_column(String(64))
    rubric_version: Mapped[int] = mapped_column(Integer)
    persona_ids: Mapped[list[str]] = mapped_column(JSON_)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    turns: Mapped[list[Turn]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    """A single presenter answer plus the artifacts the pipeline produced for it.

    ``extraction_json`` / ``score_json`` / ``reaction_json`` store the pydantic
    ``.model_dump(mode="json")`` of each object verbatim. ``reaction_json`` is
    nullable because the reply is generated after the number is locked and may not
    exist yet when the turn row is first written.
    """

    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer)
    persona_id: Mapped[str] = mapped_column(String(64))
    concern_id: Mapped[str] = mapped_column(String(64))
    user_answer: Mapped[str] = mapped_column(Text)
    extraction_json: Mapped[dict[str, Any]] = mapped_column(JSON_)
    score_json: Mapped[dict[str, Any]] = mapped_column(JSON_)
    reaction_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[RehearsalSession] = relationship(back_populates="turns")


class ClaimLedger(Base):
    """The running record of every scored claim, stored with its verbatim span so
    Tier-0 consistency checks on later turns can be rehydrated into the prompt."""

    __tablename__ = "claim_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32))
    backing: Mapped[str | None] = mapped_column(String(32), nullable=True)
    span: Mapped[str] = mapped_column(Text)


class Clarification(Base):
    """A non-scored clarifying question and the evaluator's reply.

    Kept in its own table on purpose: a clarification must never land in
    ``turns``, where ``attempts`` are counted from — storing it here means it
    cannot inflate the attempt count, advance the agenda, or move a meter. It is
    persisted only so the exchange renders in the live transcript and the
    auditable after-action report."""

    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    concern_id: Mapped[str] = mapped_column(String(64))
    persona_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)  # per-concern order for transcript render
    question: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PersonaMeter(Base):
    """Per-persona support meter. ``capped`` is sticky: once a red line is crossed
    it stays true and the meter is held at the rubric's ceiling for the session."""

    __tablename__ = "persona_meters"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    persona_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    support: Mapped[int] = mapped_column(Integer, default=50)
    capped: Mapped[bool] = mapped_column(Boolean, default=False)


class ConcernStatus(Base):
    """Per-concern coverage state: open | partial | satisfied | dodged."""

    __tablename__ = "concern_status"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    concern_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
