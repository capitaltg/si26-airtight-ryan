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
    LargeBinary,
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
    # Non-null exactly when this session is history: set by
    # `app.session_archive.archive_session` when the rehearsal finishes. Doubles
    # as the history list's sort key.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # `Report.model_dump(mode="json")` verbatim, snapshotted at archive time so
    # reading history costs no Bedrock call and the archived report stays
    # byte-identical to what the presenter saw after a content or rubric bump.
    # NULL means the snapshot was not written (the narrative call failed); the
    # read path falls back to building it on demand.
    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_, nullable=True)

    turns: Mapped[list[Turn]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    """A single presenter answer plus the artifacts the pipeline produced for it.

    ``extraction_json`` / ``score_json`` / ``reaction_json`` store the pydantic
    ``.model_dump(mode="json")`` of each object verbatim. ``reaction_json`` is
    nullable because the reply is generated after the number is locked and may not
    exist yet when the turn row is first written. ``answer_audio`` /
    ``answer_audio_content_type`` / ``transcript`` are populated only on the voice
    path (``POST /answer_audio``); they are null for a typed turn.
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
    # Populated only on the voice path (POST /answer_audio); null for a typed turn.
    # `deferred=True`: this blob (up to `settings.max_answer_audio_bytes`, 10 MiB)
    # is only ever read by the replay endpoint (`GET .../turns/{i}/audio`), but
    # `repo.get_turns` is called on nearly every request (next_concern, session
    # state, build_report); deferring keeps those reads from pulling every turn's
    # full audio blob into memory when nothing asked for it.
    answer_audio: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    answer_audio_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The question as asked, frozen here rather than re-derived at read time: a
    # content bump would otherwise rewrite an archived transcript. Nullable
    # because rows written before migration 0006 have no value.
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The persona's self-introduction, non-null only on their first prompt of
    # the session.
    prompt_intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How this turn's extraction was produced: `ExtractionProvenance` as a dict
    # (source, key, contract_version, model_id). Written for the audit trail and
    # read by nothing yet. Nullable because rows written before migration 0008
    # have no value — the same pattern `prompt` above uses.
    extraction_provenance: Mapped[dict[str, Any] | None] = mapped_column(
        JSON_, nullable=True
    )
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
    # The active prompt this clarification was asked against.
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class ModelResponseCache(Base):
    """Replay store that pins one model output per exact request (bug: rehearsals
    were non-deterministic).

    ``temperature=0`` does not make Bedrock reproducible: greedy decoding still
    varies with backend batching, floating-point order, and endpoint routing. So
    the first successful response for a given request is stored here keyed by a
    hash of the full request (model id, max_tokens, prompt/blocks, and — for a
    tool call — the tool name and schema), and every later identical request
    replays it instead of calling the model again.

    Deliberately NOT scoped to a session and NOT FK'd to ``sessions``: two
    rehearsal runs are two sessions, and the whole point is that identical input
    across runs yields identical output, so the key is the request content alone.
    The key is prompt-derived, so a content/version bump changes the bytes and
    self-invalidates the entry without a manual purge. Only validated successes
    are stored (see :mod:`app.bedrock.cache`); a failed/invalid response is never
    cached, so a retry can still fix it.
    """

    __tablename__ = "model_response_cache"

    # sha256 hex digest of the canonical request payload.
    request_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # "extract" | "react" — recorded for observability/debugging only.
    method: Mapped[str] = mapped_column(String(16))
    # {"tool_input": {...}} for extract, {"text": "..."} for react.
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON_)
    # Normalized presenter text that fed this key ("extract" and clarification
    # "react" rows only); NULL where no presenter text is part of the request.
    normalized_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExtractionPinRow(Base):
    """One pinned extraction per turn-input (see :mod:`app.pipeline.extraction_pin`).

    Separate from ``model_response_cache`` on purpose. That table keys on the
    rendered prompt and serves persona reactions; this one keys on the turn's
    inputs and is what makes the score a function of what the presenter said.
    Not FK'd to ``sessions``: the whole point is that two runs of the same input,
    in two different sessions, resolve to the same row.

    Stores the model's raw tool input, not a score. Anchoring, grounding, and
    scoring re-run on every replay, so a fix to any of those reaches pinned rows
    without a model call.

    ``model_id`` and ``extractor_contract_version`` are both hashed into
    ``input_hash`` (see :func:`app.pipeline.extraction_pin.extraction_key`), so a
    model change or a contract bump self-invalidates: the new key simply misses.
    They are stored here as provenance and as the handle for a targeted
    ``DELETE`` when someone wants to reclaim rows a rollback stranded.
    """

    __tablename__ = "extraction_pin"

    # sha256 hex of the canonical input payload (answer, persona, concern,
    # ledger, content fingerprint, extraction schema, contract version, model id).
    input_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # The validated `record_extraction` tool input, exactly as the model emitted it.
    tool_input: Mapped[dict[str, Any]] = mapped_column(JSON_)
    model_id: Mapped[str] = mapped_column(String(128))
    extractor_contract_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
