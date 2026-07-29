"""Archive-step tests: a finished rehearsal becomes history.

Runs against in-memory SQLite. The narrative model call is stubbed, so these
tests assert the snapshot is stored, the audio is dropped, and a failed (paid)
call never costs the presenter their archive.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.content.loader import Content, load_content
from app.db import repo
from app.db.models import Base
from app.pipeline import orchestrator
from app.schemas.extraction import Addressed, Extraction, SubQuestionCoverage
from app.schemas.reaction import PersonaReaction
from app.schemas.report import Report
from app.schemas.scoring import ScoreOutput
from app.session_archive import archive_session


@pytest.fixture(scope="module")
def content() -> Content:
    return load_content()


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        yield session


class StubReact:
    """The one narrative call, counted so a snapshot read can prove it did not
    happen twice."""

    def __init__(self) -> None:
        self.calls = 0

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str:
        self.calls += 1
        return "You held the technical line; tighten staffing specifics."


class RaisingReact:
    def react(self, prompt: str, *, max_tokens: int = 1024) -> str:
        raise RuntimeError("bedrock unavailable")


def _one_voice_turn(db: Session, content: Content, session_id) -> None:
    """A scored turn carrying a recording, so the audio nulling has something
    to drop."""
    concern = content.concerns["technical_approach"]
    repo.append_turn(
        db,
        session_id=session_id,
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id=concern.concern_id,
        user_answer="Here is the architecture.",
        extraction=Extraction(
            sub_question_coverage=[
                SubQuestionCoverage(id=sq.id, addressed=Addressed.full, span="covered")
                for sq in concern.sub_questions
            ]
        ),
        score=ScoreOutput(support_delta=2, matched_rows=["backed_specific"]),
        reaction=PersonaReaction(in_character_reply="Concrete.", rationale="+2 backed."),
        answer_audio=b"fake-webm-bytes",
        answer_audio_content_type="audio/webm",
        transcript="Here is the architecture.",
        prompt=concern.core_ask,
    )
    db.flush()


def test_archive_sets_ended_when_the_agenda_is_unfinished(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = StubReact()

    archive_session(db, content, client, session)

    assert session.status == "ended"
    assert session.archived_at is not None


def test_archive_sets_complete_when_every_concern_is_terminal(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    for cid in content.concerns:
        repo.set_concern_status(
            db, session_id=session.id, concern_id=cid, status="satisfied"
        )
    db.flush()

    archive_session(db, content, StubReact(), session)

    assert session.status == "complete"


def test_archive_stores_a_readable_report_snapshot(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    _one_voice_turn(db, content, session.id)
    client = StubReact()

    archive_session(db, content, client, session)

    assert client.calls == 1
    assert session.report_json is not None
    snapshot = Report.model_validate(session.report_json)
    assert snapshot.session_id == session.id
    assert snapshot.rate_stats.total_turns == 1
    assert snapshot.narrative.scored is False


def test_archive_drops_every_answer_recording(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    _one_voice_turn(db, content, session.id)

    archive_session(db, content, StubReact(), session)

    db.expire_all()
    turn = repo.get_turns(db, session.id)[0]
    assert turn.answer_audio is None
    assert turn.answer_audio_content_type is None
    # The scored artifact is the text; it stays.
    assert turn.transcript == "Here is the architecture."


def test_a_failed_narrative_call_still_archives(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    _one_voice_turn(db, content, session.id)

    archive_session(db, content, RaisingReact(), session)

    assert session.archived_at is not None
    assert session.report_json is None
    db.expire_all()
    assert repo.get_turns(db, session.id)[0].answer_audio is None


def test_archiving_twice_changes_nothing(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    _one_voice_turn(db, content, session.id)
    client = StubReact()

    archive_session(db, content, client, session)
    first_archived_at = session.archived_at
    first_snapshot = session.report_json

    archive_session(db, content, client, session)

    assert client.calls == 1
    assert session.archived_at == first_archived_at
    assert session.report_json == first_snapshot


def test_a_zero_turn_session_is_still_archived(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)

    archive_session(db, content, StubReact(), session)

    assert session.archived_at is not None
    assert session.report_json is not None
    assert Report.model_validate(session.report_json).rate_stats.total_turns == 0
