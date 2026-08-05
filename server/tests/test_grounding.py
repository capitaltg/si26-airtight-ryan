"""Grounding-filter tests: a finding the answer does not support never scores."""

from app.content.loader import Content, load_content
from app.pipeline.grounding import drop_ungrounded
from app.pipeline.scoring import score_turn
from app.schemas.content import Concern, PersonaDefinition
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

ANSWER = "We staff three named leads at contract start and the PM has twelve years of federal work."


def _fixture() -> tuple[Content, PersonaDefinition, Concern]:
    content = load_content()
    persona = content.personas["technical_evaluator"]
    concern = content.concerns["technical_approach"]
    return content, persona, concern


def _ground(extraction: Extraction) -> Extraction:
    _, persona, concern = _fixture()
    return drop_ungrounded(extraction, answer=ANSWER, concern=concern, persona=persona)


def test_fabricated_red_line_span_is_dropped_and_does_not_cap() -> None:
    content, persona, concern = _fixture()
    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="whatever",
                source_kind=RedLineSourceKind.concern_red_line,
                span="we will subcontract the entire effort",
                why="never said",
            )
        ]
    )
    grounded = _ground(extraction)
    assert grounded.red_line_hits == []
    score = score_turn(grounded, content.rubric)
    assert score.capped is False
    assert score.support_delta == 0


def test_real_red_line_span_is_kept() -> None:
    _, _, concern = _fixture()
    hit = RedLineHit(
        source_id=concern.red_lines[0].id,
        source_kind=RedLineSourceKind.concern_red_line,
        span="three named leads at contract start",
        why="grounded",
    )
    grounded = _ground(Extraction(red_line_hits=[hit]))
    assert grounded.red_line_hits == [hit]


def test_span_differing_only_in_case_and_spacing_is_kept() -> None:
    _, _, concern = _fixture()
    hit = RedLineHit(
        source_id=concern.red_lines[0].id,
        source_kind=RedLineSourceKind.concern_red_line,
        span="Three   Named\nLeads",
        why="same words, different typing",
    )
    grounded = _ground(Extraction(red_line_hits=[hit]))
    assert len(grounded.red_line_hits) == 1


def test_non_negotiable_hit_dropped_when_persona_lists_none() -> None:
    content = load_content()
    persona = content.personas["technical_evaluator"].model_copy(
        update={"non_negotiables": []}
    )
    concern = content.concerns["technical_approach"]
    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="whatever",
                source_kind=RedLineSourceKind.non_negotiable,
                span="three named leads at contract start",
                why="grounded span, but the persona has no non-negotiables",
            )
        ]
    )
    grounded = drop_ungrounded(
        extraction, answer=ANSWER, concern=concern, persona=persona
    )
    assert grounded.red_line_hits == []


def test_fabricated_claim_span_is_dropped_so_backed_commitment_pays_nothing() -> None:
    content, _, _ = _fixture()
    extraction = Extraction(
        claims=[
            Claim(
                text="We will deliver in 30 days.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="delivery within thirty days",
            )
        ]
    )
    grounded = _ground(extraction)
    assert grounded.claims == []
    assert score_turn(grounded, content.rubric).support_delta == 0


def test_coverage_with_unknown_sub_question_id_is_dropped() -> None:
    extraction = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(
                id="not_a_real_sub_question",
                addressed=Addressed.full,
                span="three named leads at contract start",
            )
        ]
    )
    assert _ground(extraction).sub_question_coverage == []


def test_addressed_coverage_without_a_span_is_dropped() -> None:
    _, _, concern = _fixture()
    real_id = concern.sub_questions[0].id
    extraction = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id=real_id, addressed=Addressed.full, span=None)
        ]
    )
    assert _ground(extraction).sub_question_coverage == []


def test_unaddressed_coverage_needs_no_span() -> None:
    _, _, concern = _fixture()
    real_id = concern.sub_questions[0].id
    row = SubQuestionCoverage(id=real_id, addressed=Addressed.none, span=None)
    assert _ground(Extraction(sub_question_coverage=[row])).sub_question_coverage == [row]


def test_dodge_with_unknown_sub_question_id_is_dropped() -> None:
    extraction = Extraction(
        dodges=[
            Dodge(
                sub_question_id="not_a_real_sub_question",
                type=DodgeType.deflection,
                answer_span="talked about something else",
            )
        ]
    )
    assert _ground(extraction).dodges == []


def test_everything_dropped_scores_zero_with_an_audit_row() -> None:
    content, _, _ = _fixture()
    extraction = Extraction(
        claims=[
            Claim(
                text="invented",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="never typed this",
            )
        ],
        dodges=[
            Dodge(
                sub_question_id="nope",
                type=DodgeType.deflection,
                answer_span="x",
            )
        ],
    )
    score = score_turn(_ground(extraction), content.rubric)
    assert score.support_delta == 0
    assert score.matched_rows == ["unsubstantiated"]


def test_invented_source_id_with_a_real_span_cannot_cap() -> None:
    content, _, _ = _fixture()
    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="not-a-real-authored-red-line",
                source_kind=RedLineSourceKind.concern_red_line,
                span="three named leads at contract start",
                why="real span, invented rule",
            )
        ]
    )
    grounded = _ground(extraction)
    assert grounded.red_line_hits == []
    score = score_turn(grounded, content.rubric)
    assert score.support_delta == 0
    assert score.capped is False


def test_authored_concern_red_line_id_is_kept() -> None:
    _, _, concern = _fixture()
    hit = RedLineHit(
        source_id=concern.red_lines[0].id,
        source_kind=RedLineSourceKind.concern_red_line,
        span="three named leads at contract start",
        why="authored id, real span",
    )
    assert _ground(Extraction(red_line_hits=[hit])).red_line_hits == [hit]


def test_authored_persona_non_negotiable_id_is_kept() -> None:
    _, persona, _ = _fixture()
    hit = RedLineHit(
        source_id=persona.non_negotiables[0].id,
        source_kind=RedLineSourceKind.non_negotiable,
        span="three named leads at contract start",
        why="authored id, real span",
    )
    assert _ground(Extraction(red_line_hits=[hit])).red_line_hits == [hit]


def test_id_valid_for_the_other_kind_is_dropped() -> None:
    _, persona, _ = _fixture()
    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id=persona.non_negotiables[0].id,
                source_kind=RedLineSourceKind.concern_red_line,
                span="three named leads at contract start",
                why="right id, wrong list",
            )
        ]
    )
    assert _ground(extraction).red_line_hits == []


def test_nothing_to_drop_returns_the_same_object() -> None:
    extraction = Extraction()
    assert _ground(extraction) is extraction


def test_dodge_with_an_ungrounded_answer_span_is_dropped() -> None:
    content, _, concern = _fixture()
    extraction = Extraction(
        dodges=[
            Dodge(
                sub_question_id=concern.sub_questions[0].id,
                type=DodgeType.non_commitment,
                answer_span="we will circle back on that later",
                explanation="invented prose that is not in the answer",
            )
        ]
    )
    grounded = _ground(extraction)
    assert grounded.dodges == []
    assert score_turn(grounded, content.rubric).support_delta == 0


def test_dodge_with_a_real_answer_span_is_kept_and_scores() -> None:
    content, _, concern = _fixture()
    dodge = Dodge(
        sub_question_id=concern.sub_questions[0].id,
        type=DodgeType.non_commitment,
        answer_span="three named leads at contract start",
        explanation="named staffing, never described the architecture",
    )
    grounded = _ground(Extraction(dodges=[dodge]))
    assert grounded.dodges == [dodge]
    assert score_turn(grounded, content.rubric).support_delta == -2
