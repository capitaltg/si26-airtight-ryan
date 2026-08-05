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

from app.bedrock.cache import CacheKeyInput
from app.content.loader import Content, load_content
from app.db import repo
from app.db.models import Base, RehearsalSession
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

_BACKED_ANSWER = "Here is a named lead, 12 years, full-time; covered."


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
        content: str | list,
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        if content_schema is Extraction:
            assert self.next_extraction is not None, "test did not script an extraction"
            return self.next_extraction
        if content_schema is PersonaReaction:
            return self.reaction
        raise AssertionError(f"unexpected schema {content_schema!r}")

    def react(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        cache_key: CacheKeyInput | None = None,
    ) -> str:
        return "Here's what I'm looking for. I still need a real answer."


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


def _dodge(concern: Concern, answer: str) -> Extraction:
    """``answer_span`` is a real slice (the whole thing) of ``answer``, the same
    text the test then submits, so a future grounding check on dodges would not
    drop it."""
    return Extraction(
        dodges=[
            Dodge(
                sub_question_id=concern.sub_questions[0].id,
                type=DodgeType.non_commitment,
                answer_span=answer,
                explanation="answered with enthusiasm, no commitment",
            )
        ]
    )


def _red_line() -> Extraction:
    return Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="on_prem_hosting",
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
    client.next_extraction = _dodge(
        content.concerns["technical_approach"], "We're excited to deliver."
    )

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

    result = orchestrator.submit_answer(db, content, client, session, _BACKED_ANSWER)

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
    first = orchestrator.submit_answer(
        db, content, client, session, "We'll just lift and shift the mainframe overnight."
    )
    assert first.capped is True
    assert first.meter == 25  # clamped to the ceiling
    assert first.concern_status == "dodged"  # red line is a terminal failure of the concern

    # next good answer lands on the same persona's next concern; the cap is sticky
    assert first.next is not None
    next_concern = first.next.concern
    client.next_extraction = _full(next_concern)
    second = orchestrator.submit_answer(db, content, client, session, _BACKED_ANSWER)
    assert second.persona_id == "technical_evaluator"
    assert second.meter == 25  # +2 would be 27, held at the ceiling
    assert second.capped is True


def test_invented_red_line_source_id_leaves_meter_and_concern_status_untouched(
    db: Session, content: Content
) -> None:
    """An invented ``source_id`` must not survive grounding, so the finding that
    would otherwise cap the meter and terminate the concern as ``dodged`` never
    reaches ``score_turn`` or ``_next_status`` at all. The turn scores exactly as
    if the model had returned nothing: no delta, no cap, and the concern gets
    another attempt like any other unaddressed first turn."""
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    client.next_extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="not-a-real-authored-red-line",
                source_kind=RedLineSourceKind.concern_red_line,
                span="we'll just lift and shift the mainframe overnight",
                why="real span, invented rule",
            )
        ]
    )

    result = orchestrator.submit_answer(
        db, content, client, session, "We'll just lift and shift the mainframe overnight."
    )

    assert result.support_delta == 0
    assert result.meter == 50  # unchanged from the starting meter
    assert result.capped is False
    assert result.concern_status != "dodged"
    assert result.concern_status == "partial"  # first attempt with no grounded finding


def test_submit_answer_with_audio_persists_it_on_the_turn(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    client.next_extraction = _full(content.concerns["technical_approach"])
    audio = orchestrator.AnswerAudio(
        data=b"\x00\x01fake-audio-bytes",
        content_type="audio/webm",
        transcript=_BACKED_ANSWER,
    )

    result = orchestrator.submit_answer(
        db, content, client, session, _BACKED_ANSWER, audio
    )

    turn = repo.get_turns(db, session.id)[0]
    assert turn.answer_audio == b"\x00\x01fake-audio-bytes"
    assert turn.answer_audio_content_type == "audio/webm"
    assert turn.transcript == _BACKED_ANSWER
    # scoring/agenda behavior is unaffected by the presence of audio
    assert result.support_delta == 2
    assert result.concern_status == "satisfied"


def test_submit_answer_without_audio_leaves_turn_audio_columns_null(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    client.next_extraction = _full(content.concerns["technical_approach"])

    orchestrator.submit_answer(db, content, client, session, _BACKED_ANSWER)

    turn = repo.get_turns(db, session.id)[0]
    assert turn.answer_audio is None
    assert turn.answer_audio_content_type is None
    assert turn.transcript is None


def test_typed_and_voice_paths_yield_equivalent_scoring(db: Session, content: Content) -> None:
    """The same words, submitted typed vs. as a transcribed voice answer, must
    produce the same score — audio only changes what gets persisted."""
    concern = content.concerns["technical_approach"]
    answer_text = _BACKED_ANSWER

    typed_session = orchestrator.start_session(db, content)
    typed_client = ScriptedClient()
    typed_client.next_extraction = _full(concern)
    typed_result = orchestrator.submit_answer(
        db, content, typed_client, typed_session, answer_text
    )

    voice_session = orchestrator.start_session(db, content)
    voice_client = ScriptedClient()
    voice_client.next_extraction = _full(concern)
    audio = orchestrator.AnswerAudio(
        data=b"\x00\x01fake-audio-bytes", content_type="audio/mp4", transcript=answer_text
    )
    voice_result = orchestrator.submit_answer(
        db, content, voice_client, voice_session, answer_text, audio
    )

    assert typed_result.support_delta == voice_result.support_delta
    assert typed_result.matched_rows == voice_result.matched_rows
    assert typed_result.meter == voice_result.meter
    assert typed_result.capped == voice_result.capped
    assert typed_result.concern_status == voice_result.concern_status

    # `ScriptedClient.extract` routes only on `content_schema`, ignoring the
    # `content` it's handed — so the equality above would hold even if the
    # voice path fed the pipeline something other than the real transcript.
    # Assert directly against what was persisted: the transcript must be what
    # both `submit_answer` scored (`user_answer`) and what's kept for replay
    # (`transcript`).
    voice_turn = repo.get_turns(db, voice_session.id)[0]
    assert voice_turn.user_answer == answer_text
    assert voice_turn.transcript == answer_text


def test_clarification_does_not_score_advance_or_count_as_attempt(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()

    before = orchestrator.next_concern(db, content, session)
    assert before is not None

    first = orchestrator.ask_clarification(db, content, client, session, "What do you mean by X?")
    assert first.reply
    assert first.remaining == 1
    # meter untouched, no turn recorded, concern statuses unchanged
    assert repo.get_meter(db, session.id, before.persona.id).support == 50
    assert repo.get_turns(db, session.id) == []
    assert all(v == "open" for v in repo.get_concern_statuses(db, session.id).values())

    # same prompt stays active — the agenda did not advance
    after = orchestrator.next_concern(db, content, session)
    assert after is not None
    assert after.concern.concern_id == before.concern.concern_id
    assert after.is_follow_up == before.is_follow_up

    # second clarification is allowed, then the cap is enforced
    second = orchestrator.ask_clarification(db, content, client, session, "And Y?")
    assert second.remaining == 0
    with pytest.raises(orchestrator.ClarificationCapReached):
        orchestrator.ask_clarification(db, content, client, session, "One more?")


def test_clarification_cap_is_per_concern(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()

    # Exhaust the first concern's clarification allowance.
    first_concern = orchestrator.next_concern(db, content, session).concern.concern_id
    orchestrator.ask_clarification(db, content, client, session, "q1")
    orchestrator.ask_clarification(db, content, client, session, "q2")

    # Satisfy the first concern so the agenda advances to a new one.
    client.next_extraction = _full(content.concerns[first_concern])
    result = orchestrator.submit_answer(db, content, client, session, _BACKED_ANSWER)
    assert result.next is not None
    assert result.next.concern.concern_id != first_concern

    # The new concern gets its own full allowance.
    fresh = orchestrator.ask_clarification(db, content, client, session, "new concern q")
    assert fresh.concern_id == result.next.concern.concern_id
    assert fresh.remaining == 1


def test_session_ends_after_all_concerns_resolved(db: Session, content: Content) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()

    submissions = 0
    while True:
        asg = orchestrator.next_concern(db, content, session)
        if asg is None:
            break
        client.next_extraction = _full(asg.concern)
        result = orchestrator.submit_answer(db, content, client, session, _BACKED_ANSWER)
        submissions += 1
        assert submissions <= 8, "should terminate within 8 satisfied concerns"

    assert submissions == 8
    assert result.done is True
    assert result.next is None
    # every concern resolved, session marked complete
    statuses = repo.get_concern_statuses(db, session.id)
    assert all(v in ("satisfied", "dodged") for v in statuses.values())


def _satisfy_current(
    db: Session, content: Content, session: RehearsalSession, client: ScriptedClient
) -> None:
    """Answer the active concern with a fully-covering, backed answer."""
    asg = orchestrator.next_concern(db, content, session)
    assert asg is not None
    client.next_extraction = _full(asg.concern)
    orchestrator.submit_answer(db, content, client, session, _BACKED_ANSWER)


def test_first_prompt_of_the_session_carries_the_personas_intro(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    asg = orchestrator.next_concern(db, content, session)

    assert asg is not None
    assert asg.persona.id == "technical_evaluator"
    assert asg.intro == content.personas["technical_evaluator"].intro


def test_intro_is_none_on_the_same_personas_next_concern(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    _satisfy_current(db, content, session, client)

    asg = orchestrator.next_concern(db, content, session)
    assert asg is not None
    assert asg.persona.id == "technical_evaluator"  # still Dana, second concern
    assert asg.concern.concern_id == "key_personnel"
    assert asg.intro is None


def test_intro_survives_a_reload_before_the_first_turn_is_answered(
    db: Session, content: Content
) -> None:
    """Derived from the turn log, so re-reading the state before answering
    still shows the intro."""
    session = orchestrator.start_session(db, content)
    first = orchestrator.next_concern(db, content, session)
    second = orchestrator.next_concern(db, content, session)

    assert first is not None and second is not None
    assert first.intro == second.intro == content.personas["technical_evaluator"].intro


def test_handoff_to_the_next_persona_carries_their_intro(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    # Walk out Dana's whole slice (technical_approach, key_personnel,
    # transition, risk) so the agenda hands off to Marcus.
    for _ in range(10):
        asg = orchestrator.next_concern(db, content, session)
        assert asg is not None
        if asg.persona.id != "technical_evaluator":
            break
        _satisfy_current(db, content, session, client)

    asg = orchestrator.next_concern(db, content, session)
    assert asg is not None
    assert asg.persona.id == "contracting_officer"
    assert asg.is_follow_up is False
    assert asg.intro == content.personas["contracting_officer"].intro

    # A dodge on Marcus's opening concern presses again on the same concern —
    # and he has now spoken, so his follow-up carries no intro.
    client.next_extraction = _dodge(asg.concern, "We'll get you that later.")
    orchestrator.submit_answer(db, content, client, session, "We'll get you that later.")
    follow_up = orchestrator.next_concern(db, content, session)
    assert follow_up is not None
    assert follow_up.persona.id == "contracting_officer"
    assert follow_up.is_follow_up is True
    assert follow_up.intro is None


def test_follow_up_on_a_personas_first_concern_carries_no_intro(
    db: Session, content: Content
) -> None:
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()
    asg = orchestrator.next_concern(db, content, session)
    assert asg is not None
    assert asg.intro is not None  # first ask has it

    client.next_extraction = _dodge(asg.concern, "We're very excited about this.")
    orchestrator.submit_answer(db, content, client, session, "We're very excited about this.")

    follow_up = orchestrator.next_concern(db, content, session)
    assert follow_up is not None
    assert follow_up.is_follow_up is True
    assert follow_up.concern.concern_id == asg.concern.concern_id
    assert follow_up.intro is None


def test_core_prompt_is_the_concern_core_ask_verbatim(db: Session, content: Content) -> None:
    """The prompt text is authored content, passed through. Nothing is prepended
    to it, so the presenter reads the question and nothing else."""
    session = orchestrator.start_session(db, content)
    asg = orchestrator.next_concern(db, content, session)

    assert asg is not None
    assert asg.prompt == content.concerns["technical_approach"].core_ask


def test_neither_prompt_kind_carries_the_speaker_label(db: Session, content: Content) -> None:
    """The reported defect was a format that changed between two consecutive
    lines from the same evaluator: the first ask on a concern was labeled and
    the press that followed it was not. Asserting both kinds in one test is what
    keeps a future re-label from reintroducing the split."""
    session = orchestrator.start_session(db, content)
    client = ScriptedClient()

    core = orchestrator.next_concern(db, content, session)
    assert core is not None
    label = f"{core.persona.display_name}:"
    assert core.is_follow_up is False
    assert not core.prompt.startswith(label)

    # A dodge presses again on the same concern, which is the follow-up kind.
    client.next_extraction = _dodge(core.concern, "We're very excited about this.")
    orchestrator.submit_answer(db, content, client, session, "We're very excited about this.")

    follow_up = orchestrator.next_concern(db, content, session)
    assert follow_up is not None
    assert follow_up.is_follow_up is True
    assert follow_up.concern.concern_id == core.concern.concern_id
    assert not follow_up.prompt.startswith(label)


def test_submit_answer_persists_the_prompt_and_intro(db: Session, content: Content) -> None:
    client = ScriptedClient()
    session = orchestrator.start_session(db, content)

    first = orchestrator.next_concern(db, content, session)
    assert first is not None
    client.next_extraction = _full(first.concern)
    orchestrator.submit_answer(db, content, client, session, "Here is the architecture.")

    stored = repo.get_turns(db, session.id)[0]
    # Byte-identical to what the presenter was shown, not re-derived.
    assert stored.prompt == first.prompt
    assert stored.prompt_intro == first.persona.intro


def test_second_turn_by_the_same_persona_stores_no_intro(
    db: Session, content: Content
) -> None:
    client = ScriptedClient()
    session = orchestrator.start_session(db, content)
    for _ in range(2):
        asg = orchestrator.next_concern(db, content, session)
        assert asg is not None
        client.next_extraction = _full(asg.concern)
        orchestrator.submit_answer(db, content, client, session, "Answered.")

    turns = repo.get_turns(db, session.id)
    assert turns[0].prompt_intro is not None
    # Dana's second concern: she already introduced herself.
    assert turns[1].persona_id == turns[0].persona_id
    assert turns[1].prompt_intro is None


def test_clarification_persists_the_prompt_it_was_asked_against(
    db: Session, content: Content
) -> None:
    client = ScriptedClient()
    session = orchestrator.start_session(db, content)
    active = orchestrator.next_concern(db, content, session)
    assert active is not None

    orchestrator.ask_clarification(db, content, client, session, "What do you mean?")

    stored = repo.get_clarifications(db, session.id)[0]
    assert stored.prompt == active.prompt
