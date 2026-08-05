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

import uuid
from typing import Any

from app.content.loader import load_content
from app.db.models import PersonaMeter, Turn
from app.pipeline.scoring import score_turn
from app.report.builder import (
    _turn_findings,
    build_report,
    build_scored_report,
    render_narrative,
)
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
from app.schemas.report import ScoredFinding


class FakeReactClient:
    """Records the narrative prompt and returns a canned recap."""

    def __init__(self, text: str = "You held three of eight concerns.") -> None:
        self.text = text
        self.prompts: list[str] = []

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return self.text


def _turn(
    index: int,
    persona: str,
    concern: str,
    ext: Extraction,
    rubric: Any,
    answer: str | None = None,
) -> Turn:
    from app.pipeline.scoring import score_turn

    score = score_turn(ext, rubric)
    return Turn(
        session_id=uuid.uuid4(),
        turn_index=index,
        persona_id=persona,
        concern_id=concern,
        user_answer=answer if answer is not None else f"answer {index}",
        extraction_json=ext.model_dump(mode="json"),
        score_json=score.model_dump(mode="json"),
        reaction_json=None,
    )


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
    assert report.coverage_counts.full == 1
    assert report.coverage_counts.partial == 0
    assert report.coverage_counts.none == 0
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

    # evidence_backed (t0), dodge (t1), red_line (t2). The contradiction on t1 has
    # no verbatim span in the schema, so it is a count, not a scored finding.
    assert [f.rubric_row for f in report.findings] == ["evidence_backed", "dodge", "red_line"]
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
    assert len(report.findings) == 3
