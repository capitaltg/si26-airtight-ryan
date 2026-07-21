"""Turn-orchestrator tests (task 10).

The control loop is code-driven: concern selection, follow-up decisions, and
session termination are pure Python; the model only classifies (extraction) and
reacts. These tests script the BedrockClient so no network is touched and the
scored number is fully determined by the extraction we hand in.
"""

from collections.abc import Iterator

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.content.loader import Content, load_content
from app.db import repo
from app.db.models import Base
from app.pipeline import orchestrator
from app.schemas.content import Concern
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    Dodge,
    DodgeType,
    Extraction,
    RedLineHit,
    RedLineSourceKind,
    SubQuestionCoverage,
)
from app.schemas.reaction import PersonaReaction


@pytest.fixture(scope="module")
def content() -> Content:
    return load_content()


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


class ScriptedClient:
    """A BedrockClient stand-in. ``next_extraction`` is set by the test before
    each ``submit_answer``; reactions are canned. It routes on the requested
    schema, exactly like the real forced-tool call."""

    def __init__(self) -> None:
        self.next_extraction: Extraction | None = None
        self.reaction = PersonaReaction(in_character_reply="Noted.", rationale="Noted.")

    def extract(
        self,
        prompt: str,
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
    ) -> BaseModel:
        if content_schema is Extraction:
            assert self.next_extraction is not None, "test did not script an extraction"
            return self.next_extraction
        if content_schema is PersonaReaction:
            return self.reaction
        raise AssertionError(f"unexpected schema {content_schema!r}")


def _full(concern: Concern) -> Extraction:
    """A backed answer that fully covers every sub-question → satisfies, +2."""
    return Extraction(
        claims=[
            Claim(
                text="A named lead is committed with specific experience.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="named lead, 12 years, full-time",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(id=sq.id, addressed=Addressed.full, span="covered")
            for sq in concern.sub_questions
        ],
    )


def _dodge(concern: Concern) -> Extraction:
    return Extraction(
        dodges=[
            Dodge(
                sub_question_id=concern.sub_questions[0].id,
                type=DodgeType.non_commitment,
                evidence="answered with enthusiasm, no commitment",
            )
        ]
    )


def _red_line() -> Extraction:
    return Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="technical_approach",
                source_kind=RedLineSourceKind.concern_red_line,
                span="we'll just lift and shift the mainframe overnight",
                why="hand-waves the migration, crossing a non-negotiable",
            )
        ]
    )


def test_start_session_initializes_meters_and_concerns(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)

    assert session.persona_ids == list(orchestrator.PERSONA_ORDER)
    assert session.rubric_version == content.rubric.version

    meters = repo.get_meters(db, session.id)
    assert len(meters) == 3
    assert all(m.support == 50 and m.capped is False for m in meters)

    statuses = repo.get_concern_statuses(db, session.id)
    assert len(statuses) == 8
    assert all(v == "open" for v in statuses.values())


def test_next_concern_follows_persona_priority_order(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    asg = orchestrator.next_concern(db, content, session)

    assert asg is not None
    # technical_evaluator is first, and technical_approach is its top priority.
    assert asg.persona.id == "technical_evaluator"
    assert asg.concern.concern_id == "technical_approach"
    assert asg.is_follow_up is False


def test_dodge_yields_same_concern_follow_up_and_drops_meter(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    client.next_extraction = _dodge(content.concerns["technical_approach"])

    result = orchestrator.submit_answer(db, content, client, session, "We're excited to deliver.")

    assert result.support_delta == -2
    assert result.meter == 48  # 50 - 2
    assert result.capped is False
    assert result.concern_status == "partial"
    assert result.done is False
    # follow-up stays on the same concern
    assert result.next is not None
    assert result.next.is_follow_up is True
    assert result.next.concern.concern_id == "technical_approach"


def test_backed_answer_satisfies_and_advances(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    client.next_extraction = _full(content.concerns["technical_approach"])

    result = orchestrator.submit_answer(db, content, client, session, "Here is the architecture...")

    assert result.support_delta == 2
    assert result.meter == 52
    assert result.concern_status == "satisfied"
    # advances to the technical evaluator's next priority
    assert result.next is not None
    assert result.next.is_follow_up is False
    assert result.next.concern.concern_id == "key_personnel"


def test_red_line_caps_and_stays_capped_across_next_good_answer(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()

    client.next_extraction = _red_line()
    first = orchestrator.submit_answer(db, content, client, session, "We'll just lift and shift.")
    assert first.capped is True
    assert first.meter == 25  # clamped to the ceiling
    assert first.concern_status == "dodged"  # red line is a terminal failure of the concern

    # next good answer lands on the same persona's next concern; the cap is sticky
    assert first.next is not None
    next_concern = first.next.concern
    client.next_extraction = _full(next_concern)
    second = orchestrator.submit_answer(db, content, client, session, "Named PM, full-time.")
    assert second.persona_id == "technical_evaluator"
    assert second.meter == 25  # +2 would be 27, held at the ceiling
    assert second.capped is True


def test_session_ends_after_all_concerns_resolved(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()

    submissions = 0
    while True:
        asg = orchestrator.next_concern(db, content, session)
        if asg is None:
            break
        client.next_extraction = _full(asg.concern)
        result = orchestrator.submit_answer(db, content, client, session, "backed answer")
        submissions += 1
        assert submissions <= 8, "should terminate within 8 satisfied concerns"

    assert submissions == 8
    assert result.done is True
    assert result.next is None
    # every concern resolved, session marked complete
    statuses = repo.get_concern_statuses(db, session.id)
    assert all(v in ("satisfied", "dodged") for v in statuses.values())
