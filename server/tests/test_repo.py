"""Persistence-layer tests (task 7).

Runs against an in-memory SQLite database so unit CI stays offline-green. The
models use portable column types (a JSON variant that becomes JSONB only on
Postgres), so the same schema round-trips here and in the real deploy. The audit
trail depends on scored artifacts persisting *verbatim* — these tests assert the
stored extraction/score/reaction reconstruct byte-for-byte, spans included.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import repo
from app.db.models import Base, ExtractionPinRow, RehearsalSession, Turn
from app.schemas.extraction import (
    Backing,
    Claim,
    ClaimType,
    Extraction,
    RedLineHit,
    RedLineSourceKind,
)
from app.schemas.reaction import PersonaReaction
from app.schemas.scoring import ScoreOutput


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        yield session


def _extraction() -> Extraction:
    return Extraction(
        claims=[
            Claim(
                text="The PM has 12 years of federal case-management experience.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="our PM brings 12 years running federal case systems",
            )
        ],
        red_line_hits=[
            RedLineHit(
                source_id="marcus_pws",
                source_kind=RedLineSourceKind.non_negotiable,
                span="we'll also handle work outside the PWS",
                why="promised work outside the stated scope",
            )
        ],
    )


def test_create_session_persists_and_reads_back(db: Session) -> None:
    created = repo.create_session(
        db,
        scenario_version="v1",
        rubric_version=1,
        persona_ids=["technical_evaluator", "contracting_officer"],
    )
    db.commit()

    fetched = repo.get_session(db, created.id)
    assert fetched is not None
    assert fetched.scenario_version == "v1"
    assert fetched.rubric_version == 1
    assert fetched.persona_ids == ["technical_evaluator", "contracting_officer"]
    assert fetched.status == "active"
    assert fetched.created_at is not None


def test_append_turn_round_trips_jsonb_verbatim(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    extraction = _extraction()
    score = ScoreOutput(support_delta=-2, matched_rows=["red_line"], capped=True)
    reaction = PersonaReaction(
        in_character_reply="That is outside the scope we asked about.",
        rationale="promising out-of-scope work crossed a non-negotiable",
    )

    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="We will deliver X, and we'll also handle work outside the PWS.",
        extraction=extraction,
        score=score,
        reaction=reaction,
    )
    db.commit()

    turns = repo.get_turns(db, session.id)
    assert len(turns) == 1
    turn = turns[0]
    assert turn.turn_index == 0
    assert turn.persona_id == "technical_evaluator"
    assert turn.concern_id == "technical_approach"
    # Verbatim round-trip: the stored blobs reconstruct the exact pydantic objects,
    # spans and all — the audit trail depends on it.
    assert Extraction.model_validate(turn.extraction_json) == extraction
    assert ScoreOutput.model_validate(turn.score_json) == score
    assert PersonaReaction.model_validate(turn.reaction_json) == reaction


def test_append_turn_persists_audio_fields_when_given(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="We will deliver X.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0, matched_rows=["unsubstantiated"], capped=False),
        reaction=None,
        answer_audio=b"\x00\x01fake-webm-bytes",
        answer_audio_content_type="audio/webm",
        transcript="We will deliver X.",
    )
    db.commit()

    turn = repo.get_turns(db, session.id)[0]
    assert turn.answer_audio == b"\x00\x01fake-webm-bytes"
    assert turn.answer_audio_content_type == "audio/webm"
    assert turn.transcript == "We will deliver X."


def test_append_turn_audio_fields_default_to_none(db: Session) -> None:
    """The text-only path (no audio kwargs passed) must leave the new columns
    null — this is what keeps ``POST /answer`` byte-identical."""
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="We will deliver X.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0, matched_rows=["unsubstantiated"], capped=False),
        reaction=None,
    )
    db.commit()

    turn = repo.get_turns(db, session.id)[0]
    assert turn.answer_audio is None
    assert turn.answer_audio_content_type is None
    assert turn.transcript is None


def test_reaction_is_optional_on_a_turn(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["program_rep"]
    )
    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="program_rep",
        concern_id="risk",
        user_answer="Our approach mitigates the top three risks.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0, matched_rows=["unsubstantiated"], capped=False),
        reaction=None,
    )
    db.commit()

    assert repo.get_turns(db, session.id)[0].reaction_json is None


def test_claim_ledger_appends_and_fetches_by_session(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    turn0 = [
        Claim(
            text="PM has 12 years of experience.",
            type=ClaimType.commitment,
            backing=Backing.backed,
            span="12 years running federal case systems",
        )
    ]
    turn1 = [
        Claim(
            text="We use an agile cadence.",
            type=ClaimType.empirical_checkable,
            span="two-week sprints",
        )
    ]
    repo.append_claims(db, session_id=session.id, turn_index=0, claims=turn0)
    repo.append_claims(db, session_id=session.id, turn_index=1, claims=turn1)
    db.commit()

    ledger = repo.get_claims(db, session.id)
    assert [row.turn_index for row in ledger] == [0, 1]
    assert ledger[0].span == "12 years running federal case systems"
    assert ledger[0].type == "commitment"
    assert ledger[0].backing == "backed"
    # a claim without backing stores NULL, not an empty string
    assert ledger[1].backing is None


def test_meter_upsert_and_concern_status(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["contracting_officer"]
    )
    sid = session.id
    co = "contracting_officer"
    repo.upsert_meter(db, session_id=sid, persona_id=co, support=50, capped=False)
    repo.upsert_meter(db, session_id=sid, persona_id=co, support=25, capped=True)
    repo.set_concern_status(db, session_id=sid, concern_id="cost_realism", status="satisfied")
    db.commit()

    meters = repo.get_meters(db, session.id)
    assert len(meters) == 1
    assert meters[0].support == 25
    assert meters[0].capped is True

    statuses = repo.get_concern_statuses(db, session.id)
    assert statuses["cost_realism"] == "satisfied"


def test_append_turn_stores_the_prompt_it_asked(db: Session) -> None:
    """The prompt is frozen on the row: re-deriving it later from content would
    let a content bump rewrite an archived transcript."""
    session = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    turn = repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="Here is the architecture.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0),
        reaction=PersonaReaction(in_character_reply="Noted.", rationale="Noted."),
        prompt="Walk me through the architecture.",
        prompt_intro="I'm Dana, the senior technical evaluator.",
    )
    db.expire_all()
    stored = repo.get_turns(db, session.id)[0]
    assert stored.id == turn.id
    assert stored.prompt == "Walk me through the architecture."
    assert stored.prompt_intro == "I'm Dana, the senior technical evaluator."


def test_append_turn_prompt_columns_default_to_null(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="Here is the architecture.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0),
        reaction=None,
    )
    db.expire_all()
    stored = repo.get_turns(db, session.id)[0]
    assert stored.prompt is None
    assert stored.prompt_intro is None


def test_append_clarification_stores_the_active_prompt(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    repo.append_clarification(
        db,
        session_id=session.id,
        concern_id="technical_approach",
        persona_id="technical_evaluator",
        seq=0,
        question="Do you mean the hosting boundary?",
        reply="I mean the whole boundary.",
        prompt="Walk me through the architecture.",
    )
    db.expire_all()
    stored = repo.get_clarifications(db, session.id)[0]
    assert stored.prompt == "Walk me through the architecture."


def test_new_session_columns_start_null(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    assert session.archived_at is None
    assert session.report_json is None


def _archived(db: Session, *, archived_at: datetime) -> uuid.UUID:
    session = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    session.archived_at = archived_at
    db.flush()
    return session.id


def test_prune_history_keeps_the_newest_archived_sessions(db: Session) -> None:
    base = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    ids = [_archived(db, archived_at=base + timedelta(minutes=i)) for i in range(7)]

    repo.prune_history(db, keep=5, abandoned_ttl_hours=24)

    surviving = {s.id for s in db.scalars(select(RehearsalSession))}
    assert surviving == set(ids[2:])  # the two oldest are gone


def test_prune_history_leaves_a_live_session_alone(db: Session) -> None:
    base = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    for i in range(6):
        _archived(db, archived_at=base + timedelta(minutes=i))
    live = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )

    repo.prune_history(db, keep=5, abandoned_ttl_hours=24)

    assert db.get(RehearsalSession, live.id) is not None


def test_prune_history_deletes_an_abandoned_session_past_its_ttl(db: Session) -> None:
    stale = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    stale.created_at = datetime.now(UTC) - timedelta(hours=48)
    fresh = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    fresh.created_at = datetime.now(UTC)
    db.flush()

    repo.prune_history(db, keep=5, abandoned_ttl_hours=24)

    assert db.get(RehearsalSession, stale.id) is None
    assert db.get(RehearsalSession, fresh.id) is not None


def test_prune_history_never_deletes_a_recent_archived_session_as_abandoned(
    db: Session,
) -> None:
    """An archived session is history regardless of age; only rule 1 can touch it."""
    old_but_archived = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    old_but_archived.created_at = datetime.now(UTC) - timedelta(hours=48)
    old_but_archived.archived_at = datetime.now(UTC)
    db.flush()

    repo.prune_history(db, keep=5, abandoned_ttl_hours=24)

    assert db.get(RehearsalSession, old_but_archived.id) is not None


def test_deleting_a_session_cascades_to_every_child_row(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="poc-v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="Here is the architecture.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0),
        reaction=None,
    )
    repo.append_claims(
        db,
        session_id=session.id,
        turn_index=0,
        claims=[
            Claim(
                text="A named lead is committed.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="named lead",
            )
        ],
    )
    repo.append_clarification(
        db,
        session_id=session.id,
        concern_id="technical_approach",
        persona_id="technical_evaluator",
        seq=0,
        question="What do you mean?",
        reply="The whole boundary.",
    )
    repo.upsert_meter(
        db, session_id=session.id, persona_id="technical_evaluator", support=52, capped=False
    )
    repo.set_concern_status(
        db, session_id=session.id, concern_id="technical_approach", status="satisfied"
    )
    db.flush()

    db.delete(session)
    db.flush()

    assert repo.get_turns(db, session.id) == []
    assert repo.get_claims(db, session.id) == []
    assert repo.get_clarifications(db, session.id) == []
    assert repo.get_meters(db, session.id) == []
    assert repo.get_concern_statuses(db, session.id) == {}


def test_append_turn_stores_extraction_provenance(db: Session) -> None:
    session = repo.create_session(
        db, scenario_version="v1", rubric_version=1, persona_ids=["technical_evaluator"]
    )
    provenance = {
        "source": "fresh",
        "key": "9f2c" + "0" * 60,
        "contract_version": 1,
        "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    }
    repo.append_turn(
        db,
        session_id=session.id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="We staff three named leads at contract start.",
        extraction=Extraction(),
        score=ScoreOutput(support_delta=0, matched_rows=["unsubstantiated"], capped=False),
        reaction=None,
        extraction_provenance=provenance,
    )
    db.commit()

    turn = repo.get_turns(db, session.id)[0]
    assert turn.extraction_provenance == provenance


def test_migration_0008_columns_match_the_orm() -> None:
    """The suite has no alembic harness, so this is what keeps the ORM and
    revision 0008 from silently disagreeing about shape. `extraction_provenance`
    is nullable (rows written before 0008 have no value); the pin's contract
    version is not (0008 clears the table first, so NOT NULL needs no default)."""
    assert Turn.__table__.c["extraction_provenance"].nullable is True
    assert ExtractionPinRow.__table__.c["extractor_contract_version"].nullable is False
