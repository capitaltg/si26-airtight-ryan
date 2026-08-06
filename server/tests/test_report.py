"""After-action report tests (task 12).

The scored part of the report is 100% code-rendered from the stored turns:
per-persona meters, coverage counts, dodge counts by type, contradiction count,
and length-independent rate stats that lead. Every scored *finding* carries a
verbatim span and the rubric row it fired. The model narrative sits under a
"Not scored" header and never feeds a number — it is produced by a single
``react`` call over the already-computed summary.

These tests build ``Turn``/``PersonaMeter`` ORM objects in memory (no DB, no
network) and use a fake client for the narrative.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from app.content.loader import load_content
from app.db.models import PersonaMeter, Turn
from app.pipeline.scoring import apply_limit_penalty, score_turn
from app.report.builder import (
    _turn_findings,
    build_report,
    build_scored_report,
    render_narrative,
)
from app.schemas.content import NonNegotiable
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    ConsistencyFlag,
    Dodge,
    DodgeType,
    Extraction,
    FactCheck,
    RedLineHit,
    RedLineSourceKind,
    SourceDocument,
    SubQuestionCoverage,
    Verdict,
)
from app.schemas.report import ScoredFinding, ScoredReport
from app.schemas.scoring import LimitKind, LimitMeasurement, ScoreOutput


class FakeReactClient:
    """Records the narrative prompt and returns a canned recap."""

    def __init__(self, text: str = "You held three of eight concerns.") -> None:
        self.text = text
        self.prompts: list[str] = []

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return self.text


def _turn(
    index: int = 0,
    persona: str = "technical_evaluator",
    concern_id: str = "technical_approach",
    ext: Extraction | None = None,
    rubric: Any = None,
    answer: str | None = None,
) -> Turn:
    from app.pipeline.scoring import score_turn

    ext = ext if ext is not None else Extraction()
    rubric = rubric if rubric is not None else load_content().rubric
    score = score_turn(ext, rubric)
    return Turn(
        session_id=uuid.uuid4(),
        turn_index=index,
        persona_id=persona,
        concern_id=concern_id,
        user_answer=answer if answer is not None else f"answer {index}",
        extraction_json=ext.model_dump(mode="json"),
        score_json=score.model_dump(mode="json"),
        reaction_json=None,
    )


def _values() -> dict[str, int]:
    return {row.id: row.support_value for row in load_content().rubric.rows}


def _fixture() -> tuple[uuid.UUID, list[Turn], list[PersonaMeter], dict[str, str], Any]:
    content = load_content()
    rubric = content.rubric
    session_id = uuid.uuid4()

    # Turn 0: backed commitment + full coverage -> evidence_backed (+2).
    t0 = _turn(
        0,
        "technical_evaluator",
        "technical_approach",
        Extraction(
            claims=[
                Claim(
                    text="A named PM leads the effort.",
                    type=ClaimType.commitment,
                    backing=Backing.backed,
                    span="a named PM with twelve years",
                )
            ],
            sub_question_coverage=[
                SubQuestionCoverage(id="architecture", addressed=Addressed.full, span="phased plan")
            ],
        ),
        rubric,
    )
    # Turn 1: a dodge AND a Tier-0 contradiction -> dodge + contradiction.
    t1_answer = "We're excited about staffing and will figure out the names later."
    t1 = _turn(
        1,
        "contracting_officer",
        "key_personnel",
        Extraction(
            dodges=[
                Dodge(
                    sub_question_id="named_leads",
                    type=DodgeType.non_commitment,
                    answer_span="figure out the names later",
                    explanation="lots of enthusiasm, no names",
                )
            ],
            consistency_flags=[
                ConsistencyFlag(
                    conflicts_with_turn=0,
                    current_answer_span="figure out the names later",
                    prior_answer_span="three named leads at contract start",
                    acknowledged_revision=False,
                    explanation="contradicts earlier staffing claim",
                )
            ],
        ),
        rubric,
        answer=t1_answer,
    )
    # Turn 2: a crossed red line -> capped.
    t2 = _turn(
        2,
        "program_rep",
        "transition",
        Extraction(
            red_line_hits=[
                RedLineHit(
                    source_id="transition_rl",
                    source_kind=RedLineSourceKind.concern_red_line,
                    span="we'll skip the parallel run",
                    why="promised to skip the mandatory parallel run",
                )
            ]
        ),
        rubric,
    )

    meters = [
        PersonaMeter(
            session_id=session_id, persona_id="technical_evaluator", support=52, capped=False
        ),
        PersonaMeter(
            session_id=session_id, persona_id="contracting_officer", support=47, capped=False
        ),
        PersonaMeter(session_id=session_id, persona_id="program_rep", support=25, capped=True),
    ]
    concern_statuses = {
        "technical_approach": "satisfied",
        "key_personnel": "dodged",
        "transition": "dodged",
    }
    return session_id, [t0, t1, t2], meters, concern_statuses, content


def _turns_fixture() -> list[Turn]:
    """The turns half of ``_fixture()``, for tests that only need the turns."""
    _, turns, _, _, _ = _fixture()
    return turns


def _build_report_over_turns() -> ScoredReport:
    """Build a scored report over ``_fixture()``'s turns, unmodified."""
    session_id, turns, meters, statuses, content = _fixture()
    return build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )


def test_score_audit_agrees_on_a_normal_build() -> None:
    report = _build_report_over_turns()
    assert report.score_audit_agrees is True
    assert [a.turn_index for a in report.score_audit] == list(range(len(report.score_audit)))
    assert all(a.agrees for a in report.score_audit)


def test_score_audit_reports_a_turn_whose_persisted_number_disagrees() -> None:
    turns = _turns_fixture()
    tampered = dict(turns[0].score_json)
    tampered["support_delta"] = tampered["support_delta"] - 1
    turns[0].score_json = tampered

    report = build_scored_report(
        session_id=turns[0].session_id,
        status="complete",
        turns=turns,
        meters=[],
        concern_statuses={},
        content=load_content(),
    )
    assert report.score_audit_agrees is False
    assert report.score_audit[0].agrees is False
    assert (
        report.score_audit[0].persisted_support_delta
        != report.score_audit[0].recomputed_support_delta
    )


def test_score_audit_reproduces_the_limit_penalty() -> None:
    """The audit recomputes ``apply_limit_penalty`` too, not just ``score_turn``'s
    row combination: a turn that landed over its word limit must reproduce the
    same over_limit deduction from its stored measurement, independently."""
    content = load_content()
    rubric = content.rubric
    ext = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="architecture", addressed=Addressed.full, span="three services")
        ]
    )
    base_score = score_turn(ext, rubric)
    measurement = LimitMeasurement(
        kind=LimitKind.text_words, measured=240, warning_threshold=150, limit_threshold=200
    )
    persisted_score = apply_limit_penalty(base_score, rubric, measurement)
    assert persisted_score.limit is not None
    assert persisted_score.limit.penalty_applied is True
    assert persisted_score.support_delta == base_score.support_delta - 1  # over_limit is -1

    turn = Turn(
        session_id=uuid.uuid4(),
        turn_index=0,
        persona_id="technical_evaluator",
        concern_id="technical_approach",
        user_answer="word " * 240,
        extraction_json=ext.model_dump(mode="json"),
        score_json=persisted_score.model_dump(mode="json"),
        reaction_json=None,
    )

    report = build_scored_report(
        session_id=turn.session_id,
        status="complete",
        turns=[turn],
        meters=[],
        concern_statuses={},
        content=content,
    )

    assert report.score_audit_agrees is True
    audit = report.score_audit[0]
    assert audit.agrees is True
    assert audit.persisted_support_delta == persisted_score.support_delta
    assert audit.recomputed_support_delta == persisted_score.support_delta
    assert "over_limit" in audit.recomputed_matched_rows


def test_scored_report_counts_match_hand_computed() -> None:
    session_id, turns, meters, statuses, content = _fixture()

    report = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )

    assert report.rate_stats.total_turns == 3
    assert report.rate_stats.dodge_count == 1
    assert report.rate_stats.contradiction_count == 1
    # length-independent lead stats
    assert report.rate_stats.dodges_per_turn == round(1 / 3, 4)
    assert report.rate_stats.concerns_total == 3
    assert report.rate_stats.concerns_satisfied == 1
    assert report.rate_stats.coverage_rate == round(1 / 3, 4)

    assert report.contradiction_count == 1
    # each authored sub-question of the three concerns on the agenda, counted once
    assert report.coverage_counts.full == 1
    assert report.coverage_counts.partial == 0
    assert report.coverage_counts.none == 6
    assert report.dodge_counts_by_type == {"non_commitment": 1}

    # per-persona meters carry the cap status
    pinned = {p.persona_id: p for p in report.personas}
    assert pinned["program_rep"].capped is True
    assert pinned["technical_evaluator"].support == 52


def test_every_scored_finding_has_a_verbatim_span_and_a_rubric_row() -> None:
    session_id, turns, meters, statuses, content = _fixture()

    report = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )

    # evidence_backed (t0), dodge + contradiction (t1), red_line (t2). Both t1
    # rows now carry a verbatim span: the dodge's answer_span and the
    # contradiction's current_answer_span (countered by its prior_answer_span).
    assert [f.rubric_row for f in report.findings] == [
        "evidence_backed",
        "dodge",
        "contradiction",
        "red_line",
    ]
    valid_rows = {row.id for row in content.rubric.rows}
    for f in report.findings:
        assert f.evidence, "every scored finding must carry at least one quote"
        assert all(e.span.strip() for e in f.evidence), "every quote must be verbatim, non-empty"
        assert f.count >= 1
        assert f.rubric_row in valid_rows
        assert f.turn_index in (0, 1, 2)


def test_one_finding_per_row_carries_every_span() -> None:
    content = load_content()
    ext = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="architecture", addressed=Addressed.full, span="three services"),
            SubQuestionCoverage(id="hosting", addressed=Addressed.full, span="FedRAMP host"),
            SubQuestionCoverage(id="integrations", addressed=Addressed.partial, span="two APIs"),
        ]
    )
    findings = _turn_findings(
        _turn(0, "technical_evaluator", "technical_approach", ext, content.rubric),
        ext,
        score_turn(ext, content.rubric),
        {row.id: row.support_value for row in content.rubric.rows},
        content,
    )
    assert [f.rubric_row for f in findings] == ["approach_cited"]
    assert findings[0].count == 1
    assert findings[0].support_value == 1
    assert [e.span for e in findings[0].evidence] == ["three services", "FedRAMP host", "two APIs"]


def test_false_fact_finding_count_matches_the_applications() -> None:
    content = load_content()
    answer = "We process about 12M records and expect a six week cutover."
    ext = Extraction(
        fact_checks=[
            FactCheck(
                claim="claims 12M records",
                answer_span="12M records",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="PWS 3.1 states approximately 42 million records",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="claims a six week cutover",
                answer_span="six week cutover",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="PWS 3.4 requires a 90-day cutover window",
                tier=1,
                verdict=Verdict.refuted,
            ),
        ]
    )
    findings = _turn_findings(
        _turn(0, "technical_evaluator", "technical_approach", ext, content.rubric, answer=answer),
        ext,
        score_turn(ext, content.rubric),
        {row.id: row.support_value for row in content.rubric.rows},
        content,
    )
    assert len(findings) == 1
    assert findings[0].count == 2
    assert findings[0].support_value == -1
    assert len(findings[0].evidence) == 2


def test_tier_zero_refutation_never_becomes_a_false_fact_span() -> None:
    content = load_content()
    answer = "We process 12M records with forty staff on site."
    ext = Extraction(
        fact_checks=[
            FactCheck(
                claim="claims 12M records",
                answer_span="12M records",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="PWS 3.1 states approximately 42 million records",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="claims forty staff",
                answer_span="forty staff",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="turn 1 ledger",
                tier=0,
                verdict=Verdict.refuted,
            ),
        ]
    )
    score = score_turn(ext, content.rubric)
    findings = _turn_findings(
        _turn(0, "technical_evaluator", "technical_approach", ext, content.rubric, answer=answer),
        ext,
        score,
        {row.id: row.support_value for row in content.rubric.rows},
        content,
    )
    assert score.row_counts == {"false_fact": 1}
    assert len(findings) == 1
    assert findings[0].count == 1
    assert [e.span for e in findings[0].evidence] == ["12M records"]


def test_legacy_finding_shape_upgrades_to_grouped_evidence() -> None:
    legacy = ScoredFinding.model_validate(
        {
            "turn_index": 0,
            "persona_id": "technical_evaluator",
            "concern_id": "technical_approach",
            "rubric_row": "dodge",
            "support_value": -2,
            "span": "we are confident in our approach",
            "detail": "non_commitment",
        }
    )
    assert legacy.count == 1
    assert [(e.span, e.detail) for e in legacy.evidence] == [
        ("we are confident in our approach", "non_commitment")
    ]


def test_scored_part_is_byte_identical_across_regeneration() -> None:
    session_id, turns, meters, statuses, content = _fixture()

    a = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )
    b = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )
    assert a.model_dump_json() == b.model_dump_json()


def test_narrative_is_tagged_not_scored_and_never_carries_a_number() -> None:
    session_id, turns, meters, statuses, content = _fixture()
    scored = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )
    client = FakeReactClient()

    narrative = render_narrative(scored, content, client)

    assert narrative.scored is False
    assert narrative.header == "Not scored"
    assert narrative.text == client.text
    # exactly one model call produced the recap
    assert len(client.prompts) == 1


def test_build_report_bundles_scored_and_narrative() -> None:
    session_id, turns, meters, statuses, content = _fixture()
    client = FakeReactClient()

    report = build_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
        client=client,
    )

    assert report.narrative.scored is False
    assert report.rate_stats.total_turns == 3
    assert len(report.findings) == 4


def test_red_line_finding_carries_the_authored_rule_not_model_text() -> None:
    content = load_content()
    concern = content.concerns["technical_approach"]
    red_line = concern.red_lines[0]
    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id=red_line.id,
                source_kind=RedLineSourceKind.concern_red_line,
                span="we will host it on premises",
                why="the PWS forbids on-premises hosting",
            )
        ]
    )
    score = ScoreOutput(
        support_delta=-2,
        raw_support_delta=-2,
        matched_rows=["red_line"],
        row_counts={"red_line": 1},
        capped=True,
    )
    findings = _turn_findings(
        _turn(concern_id="technical_approach"), extraction, score, _values(), content
    )
    evidence = findings[0].evidence[0]
    assert evidence.span == "we will host it on premises"
    assert evidence.counter_span == red_line.text
    assert evidence.counter_label == f"concern_red_line: {red_line.id}"


def test_non_negotiable_finding_scopes_lookup_to_the_turns_own_persona() -> None:
    """Regression test for a cross-persona id collision.

    ``slug_id`` only dedupes a non-negotiable's id within one persona, so two
    personas can end up sharing an id (e.g. an editor customizing both). If
    ``_authored_rule`` searched every persona's non-negotiables instead of
    just the turn's own, it could return whichever persona's rule text
    happened to come first in dict iteration order -- the wrong persona's
    text, silently, in a printed report.
    """
    content = load_content()
    technical_evaluator = content.personas["technical_evaluator"]
    own_rule = technical_evaluator.non_negotiables[0]

    contracting_officer = content.personas["contracting_officer"]
    collided_contracting_officer = contracting_officer.model_copy(
        update={
            "non_negotiables": [
                NonNegotiable(id=own_rule.id, text="a different persona's rule text"),
                *contracting_officer.non_negotiables[1:],
            ]
        }
    )
    content = dataclasses.replace(
        content,
        personas={**content.personas, "contracting_officer": collided_contracting_officer},
    )
    # contracting_officer precedes technical_evaluator in dict iteration order
    # (personas load sorted by filename), so a lookup that searched every
    # persona instead of scoping to the turn's own would find the collided
    # rule first and return the wrong persona's text.
    assert list(content.personas) == ["contracting_officer", "program_rep", "technical_evaluator"]

    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id=own_rule.id,
                source_kind=RedLineSourceKind.non_negotiable,
                span="we will simply lift and shift the mainframe data overnight",
                why="hand-waves the migration",
            )
        ]
    )
    score = ScoreOutput(
        support_delta=-2,
        raw_support_delta=-2,
        matched_rows=["red_line"],
        row_counts={"red_line": 1},
        capped=True,
    )
    findings = _turn_findings(
        _turn(persona="technical_evaluator", concern_id="technical_approach"),
        extraction,
        score,
        _values(),
        content,
    )
    evidence = findings[0].evidence[0]
    assert evidence.counter_span == own_rule.text
    assert evidence.counter_span != "a different persona's rule text"
    assert evidence.counter_label == f"non_negotiable: {own_rule.id}"


def test_contradiction_is_a_finding_with_both_sides() -> None:
    content = load_content()
    extraction = Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=1,
                current_answer_span="three named leads at contract start",
                prior_answer_span="we have not identified the leads yet",
                acknowledged_revision=False,
                explanation="named leads now, none earlier",
            )
        ]
    )
    score = ScoreOutput(
        support_delta=-1,
        raw_support_delta=-1,
        matched_rows=["contradiction"],
        row_counts={"contradiction": 1},
        capped=False,
    )
    findings = _turn_findings(_turn(), extraction, score, _values(), content)
    assert [f.rubric_row for f in findings] == ["contradiction"]
    evidence = findings[0].evidence[0]
    assert evidence.span == "three named leads at contract start"
    assert evidence.counter_span == "we have not identified the leads yet"
    assert evidence.counter_label == "turn 2"


def test_false_fact_finding_quotes_the_answer_and_the_source() -> None:
    content = load_content()
    extraction = Extraction(
        fact_checks=[
            FactCheck(
                claim="claims roughly 25 million records",
                answer_span="roughly 25 million case records",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="approximately 42 million case records",
                tier=1,
                verdict=Verdict.refuted,
            )
        ]
    )
    score = ScoreOutput(
        support_delta=-1,
        raw_support_delta=-1,
        matched_rows=["false_fact"],
        row_counts={"false_fact": 1},
        capped=False,
    )
    findings = _turn_findings(_turn(), extraction, score, _values(), content)
    evidence = findings[0].evidence[0]
    assert evidence.span == "roughly 25 million case records"
    assert evidence.detail == "claims roughly 25 million records"
    assert evidence.counter_span == "approximately 42 million case records"
    assert evidence.counter_label == "rfp_pws"


def test_every_charged_row_across_a_session_carries_verified_evidence() -> None:
    """Acceptance criterion 5: no non-zero matched row exists without a verified
    evidence object. Walk a session that charges every kind the rubric supports
    -- evidence_backed, approach_cited, dodge, contradiction, red_line, and
    false_fact -- and prove each one produced a finding, and that every finding
    whose row has a non-zero support value carries at least one evidence entry."""
    content = load_content()
    rubric = content.rubric
    red_line = content.concerns["technical_approach"].red_lines[0]

    turns = [
        _turn(  # evidence_backed
            0,
            "technical_evaluator",
            "technical_approach",
            Extraction(
                claims=[
                    Claim(
                        text="A named PM leads the effort.",
                        type=ClaimType.commitment,
                        backing=Backing.backed,
                        span="a named PM with twelve years",
                    )
                ]
            ),
            rubric,
        ),
        _turn(  # approach_cited (coverage only, no backed commitment)
            1,
            "technical_evaluator",
            "technical_approach",
            Extraction(
                sub_question_coverage=[
                    SubQuestionCoverage(
                        id="architecture", addressed=Addressed.full, span="three services"
                    )
                ]
            ),
            rubric,
        ),
        _turn(  # dodge
            2,
            "contracting_officer",
            "key_personnel",
            Extraction(
                dodges=[
                    Dodge(
                        sub_question_id="named_leads",
                        type=DodgeType.non_commitment,
                        answer_span="figure out the names later",
                        explanation="lots of enthusiasm, no names",
                    )
                ]
            ),
            rubric,
            answer="We're excited about staffing and will figure out the names later.",
        ),
        _turn(  # contradiction, naming turn 2 above
            3,
            "contracting_officer",
            "key_personnel",
            Extraction(
                consistency_flags=[
                    ConsistencyFlag(
                        conflicts_with_turn=2,
                        current_answer_span="figure out the names later",
                        prior_answer_span="three named leads at contract start",
                        acknowledged_revision=False,
                        explanation="contradicts earlier staffing claim",
                    )
                ]
            ),
            rubric,
        ),
        _turn(  # red_line
            4,
            "program_rep",
            "technical_approach",
            Extraction(
                red_line_hits=[
                    RedLineHit(
                        source_id=red_line.id,
                        source_kind=RedLineSourceKind.concern_red_line,
                        span="we will host it on premises",
                        why="the PWS forbids on-premises hosting",
                    )
                ]
            ),
            rubric,
        ),
        _turn(  # false_fact
            5,
            "program_rep",
            "transition",
            Extraction(
                fact_checks=[
                    FactCheck(
                        claim="claims 12M records",
                        answer_span="12M records",
                        source_document_id=SourceDocument.rfp_pws,
                        source_quote="PWS 3.1 states approximately 42 million records",
                        tier=1,
                        verdict=Verdict.refuted,
                    )
                ]
            ),
            rubric,
            answer="We process about 12M records this year.",
        ),
    ]
    meters = [
        PersonaMeter(session_id=turns[0].session_id, persona_id=p, support=50, capped=False)
        for p in ("technical_evaluator", "contracting_officer", "program_rep")
    ]
    statuses = {"technical_approach": "dodged", "key_personnel": "dodged", "transition": "partial"}

    report = build_scored_report(
        session_id=turns[0].session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )

    rows_seen = {f.rubric_row for f in report.findings}
    assert rows_seen == {
        "evidence_backed",
        "approach_cited",
        "dodge",
        "contradiction",
        "red_line",
        "false_fact",
    }
    for f in report.findings:
        if f.support_value != 0:
            assert f.evidence, f"{f.rubric_row} charged {f.support_value} with no evidence"
            assert all(e.span.strip() for e in f.evidence)


def _report_with_statuses(statuses: dict[str, str]) -> ScoredReport:
    """A report over the standard fixture's turns with hand-set concern statuses.

    The turns and the statuses are independent inputs to `build_scored_report`, so
    a status vocabulary can be exercised without hand-building turns for it.
    """
    session_id, turns, meters, _, content = _fixture()
    return build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses=statuses,
        content=content,
    )


def test_headline_counts_only_satisfied_concerns() -> None:
    report = _report_with_statuses(
        {
            "technical_approach": "satisfied",
            "key_personnel": "partial_exhausted",
            "transition": "dodged",
            "past_performance": "breached",
        }
    )
    rs = report.rate_stats
    assert rs.concerns_total == 4
    assert rs.concerns_satisfied == 1
    assert rs.coverage_rate == 0.25
    assert rs.concerns_by_status == {
        "satisfied": 1,
        "partial_exhausted": 1,
        "dodged": 1,
        "breached": 1,
    }


def test_the_four_terminal_states_are_always_present_in_order() -> None:
    """Zeros included, so the report's shape does not depend on how the rehearsal
    went and the UI never has to invent a missing row."""
    report = _report_with_statuses({"technical_approach": "satisfied"})
    assert list(report.rate_stats.concerns_by_status.items()) == [
        ("satisfied", 1),
        ("partial_exhausted", 0),
        ("dodged", 0),
        ("breached", 0),
    ]


def test_a_status_outside_the_terminal_vocabulary_is_counted_not_dropped() -> None:
    """A session ended early leaves concerns `open`/`partial`, and archived
    sessions predate the split. Neither may silently vanish from the breakdown."""
    report = _report_with_statuses(
        {"technical_approach": "satisfied", "key_personnel": "open", "transition": "partial"}
    )
    counts = report.rate_stats.concerns_by_status
    assert counts["open"] == 1
    assert counts["partial"] == 1
    assert sum(counts.values()) == report.rate_stats.concerns_total


def test_the_narrative_prompt_separates_finishing_from_satisfying() -> None:
    session_id, turns, meters, _, content = _fixture()
    scored = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses={
            "technical_approach": "satisfied",
            "key_personnel": "partial_exhausted",
            "transition": "breached",
        },
        content=content,
    )
    client = FakeReactClient()
    render_narrative(scored, content, client)

    prompt = client.prompts[0]
    assert "Concerns satisfied: 1 of 3" in prompt
    assert "partial (attempts used) 1" in prompt
    assert "red line crossed 1" in prompt
    assert "does not mean the rubric was met" in prompt


def test_a_clean_rehearsal_reports_no_other_outcomes() -> None:
    """The model is never handed a dangling label to interpret."""
    session_id, turns, meters, _, content = _fixture()
    scored = build_scored_report(
        session_id=session_id,
        status="complete",
        turns=turns,
        meters=meters,
        concern_statuses={"technical_approach": "satisfied"},
        content=content,
    )
    client = FakeReactClient()
    render_narrative(scored, content, client)
    assert "Other outcomes: none" in client.prompts[0]


def _coverage_over(turns: list[Turn], statuses: dict[str, str]) -> Any:
    content = load_content()
    report = build_scored_report(
        session_id=turns[0].session_id,
        status="complete",
        turns=turns,
        meters=[],
        concern_statuses=statuses,
        content=content,
    )
    return report.coverage_counts


def _coverage_turn(index: int, sub_question_id: str, addressed: Addressed) -> Turn:
    """A technical_approach turn reporting exactly one sub-question outcome."""
    return _turn(
        index,
        "technical_evaluator",
        "technical_approach",
        Extraction(
            sub_question_coverage=[
                SubQuestionCoverage(id=sub_question_id, addressed=addressed, span="covered")
            ]
        ),
    )


def test_a_follow_up_does_not_count_the_same_sub_question_twice() -> None:
    """The double-count this task exists to fix: two attempts on one concern, the
    same sub-question reported `full` on both, is one covered sub-question."""
    turns = [
        _coverage_turn(0, "architecture", Addressed.full),
        _coverage_turn(1, "architecture", Addressed.full),
    ]
    cov = _coverage_over(turns, {"technical_approach": "partial_exhausted"})
    assert cov.full == 1
    # technical_approach authors three sub-questions; the other two went unanswered
    assert cov.none == 2
    assert cov.partial == 0


def test_a_sub_question_covered_on_the_first_attempt_stays_covered() -> None:
    """The follow-up prompt names only what did not land, so the second extraction
    routinely omits what did. Reading the last attempt alone would demote it."""
    turns = [
        _coverage_turn(0, "architecture", Addressed.full),
        _coverage_turn(1, "hosting", Addressed.full),
    ]
    cov = _coverage_over(turns, {"technical_approach": "partial_exhausted"})
    assert (cov.full, cov.partial, cov.none) == (2, 0, 1)


def test_a_sub_question_upgraded_on_the_follow_up_counts_once_at_its_best() -> None:
    turns = [
        _coverage_turn(0, "architecture", Addressed.partial),
        _coverage_turn(1, "architecture", Addressed.full),
    ]
    cov = _coverage_over(turns, {"technical_approach": "partial_exhausted"})
    assert (cov.full, cov.partial, cov.none) == (1, 0, 2)


def test_a_concern_that_never_got_an_answer_still_has_a_denominator() -> None:
    """Every sub-question on the agenda is accounted for, so `full + partial +
    none` is a count of sub-questions rather than of extraction rows."""
    turns = [_coverage_turn(0, "architecture", Addressed.full)]
    content = load_content()
    statuses = {"technical_approach": "partial_exhausted", "key_personnel": "open"}
    cov = _coverage_over(turns, statuses)
    expected = sum(len(content.concerns[cid].sub_questions) for cid in statuses)
    assert cov.full + cov.partial + cov.none == expected  # 3 + 2
    assert (cov.full, cov.partial, cov.none) == (1, 0, 4)
