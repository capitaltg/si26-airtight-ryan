"""Repository functions over the runtime state models (task 7).

Thin, typed helpers around a SQLAlchemy ``Session``. Callers own the transaction
boundary (commit/rollback) so the orchestrator can persist a whole turn
atomically. Pydantic artifacts are stored via ``model_dump(mode="json")`` and
read back verbatim — no summarization of scored artifacts.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ClaimLedger,
    ConcernStatus,
    PersonaMeter,
    RehearsalSession,
    Turn,
)
from app.schemas.extraction import Claim, Extraction
from app.schemas.reaction import PersonaReaction
from app.schemas.scoring import ScoreOutput


def create_session(
    db: Session,
    *,
    scenario_version: str,
    rubric_version: int,
    persona_ids: list[str],
) -> RehearsalSession:
    session = RehearsalSession(
        scenario_version=scenario_version,
        rubric_version=rubric_version,
        persona_ids=list(persona_ids),
        status="active",
    )
    db.add(session)
    db.flush()  # populate id/created_at without forcing the caller's commit
    return session


def get_session(db: Session, session_id: uuid.UUID) -> RehearsalSession | None:
    return db.get(RehearsalSession, session_id)


def append_turn(
    db: Session,
    *,
    session_id: uuid.UUID,
    turn_index: int,
    persona_id: str,
    concern_id: str,
    user_answer: str,
    extraction: Extraction,
    score: ScoreOutput,
    reaction: PersonaReaction | None,
) -> Turn:
    turn = Turn(
        session_id=session_id,
        turn_index=turn_index,
        persona_id=persona_id,
        concern_id=concern_id,
        user_answer=user_answer,
        extraction_json=extraction.model_dump(mode="json"),
        score_json=score.model_dump(mode="json"),
        reaction_json=reaction.model_dump(mode="json") if reaction is not None else None,
    )
    db.add(turn)
    db.flush()
    return turn


def get_turns(db: Session, session_id: uuid.UUID) -> list[Turn]:
    stmt = (
        select(Turn)
        .where(Turn.session_id == session_id)
        .order_by(Turn.turn_index, Turn.created_at)
    )
    return list(db.scalars(stmt))


def append_claims(
    db: Session,
    *,
    session_id: uuid.UUID,
    turn_index: int,
    claims: list[Claim],
) -> list[ClaimLedger]:
    rows = [
        ClaimLedger(
            session_id=session_id,
            turn_index=turn_index,
            text=claim.text,
            type=claim.type.value,
            backing=claim.backing.value if claim.backing is not None else None,
            span=claim.span,
        )
        for claim in claims
    ]
    db.add_all(rows)
    db.flush()
    return rows


def get_claims(db: Session, session_id: uuid.UUID) -> list[ClaimLedger]:
    stmt = (
        select(ClaimLedger)
        .where(ClaimLedger.session_id == session_id)
        .order_by(ClaimLedger.turn_index, ClaimLedger.id)
    )
    return list(db.scalars(stmt))


def upsert_meter(
    db: Session,
    *,
    session_id: uuid.UUID,
    persona_id: str,
    support: int,
    capped: bool,
) -> PersonaMeter:
    meter = db.get(PersonaMeter, (session_id, persona_id))
    if meter is None:
        meter = PersonaMeter(session_id=session_id, persona_id=persona_id)
        db.add(meter)
    meter.support = support
    meter.capped = capped
    db.flush()
    return meter


def get_meter(
    db: Session, session_id: uuid.UUID, persona_id: str
) -> PersonaMeter | None:
    return db.get(PersonaMeter, (session_id, persona_id))


def get_meters(db: Session, session_id: uuid.UUID) -> list[PersonaMeter]:
    stmt = (
        select(PersonaMeter)
        .where(PersonaMeter.session_id == session_id)
        .order_by(PersonaMeter.persona_id)
    )
    return list(db.scalars(stmt))


def set_concern_status(
    db: Session,
    *,
    session_id: uuid.UUID,
    concern_id: str,
    status: str,
) -> ConcernStatus:
    row = db.get(ConcernStatus, (session_id, concern_id))
    if row is None:
        row = ConcernStatus(session_id=session_id, concern_id=concern_id)
        db.add(row)
    row.status = status
    db.flush()
    return row


def get_concern_statuses(db: Session, session_id: uuid.UUID) -> dict[str, str]:
    stmt = select(ConcernStatus).where(ConcernStatus.session_id == session_id)
    return {row.concern_id: row.status for row in db.scalars(stmt)}
