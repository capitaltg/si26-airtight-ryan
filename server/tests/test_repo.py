"""Persistence-layer tests (task 7).

Runs against an in-memory SQLite database so unit CI stays offline-green. The
models use portable column types (a JSON variant that becomes JSONB only on
Postgres), so the same schema round-trips here and in the real deploy. The audit
trail depends on scored artifacts persisting *verbatim* — these tests assert the
stored extraction/score/reaction reconstruct byte-for-byte, spans included.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import repo
from app.db.models import Base
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
