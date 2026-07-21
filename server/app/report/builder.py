"""After-action report builder (task 12).

The scored part is rendered entirely in code from the stored turns — no model
touches a number here. ``build_scored_report`` is pure and deterministic:
regenerating it from the same turns is byte-identical. The single model call
lives in ``render_narrative``, which produces a coaching recap tagged
``scored=False``; it reads the already-computed summary and never sets a score.

Findings vs counts
------------------
A ``ScoredFinding`` must carry a verbatim span, so it is emitted only for the
signals that carry one: ``red_line`` (hit span), ``dodge`` (evidence),
``evidence_backed`` (the backed claim's span), ``approach_cited`` (coverage
span), and ``false_fact`` (the checked claim). ``contradiction`` and
``unsubstantiated`` have no verbatim span in the extraction schema, so they are
surfaced as counts instead — never as a spanless "scored line".
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Protocol

from app.content.loader import Content
from app.db.models import PersonaMeter, Turn
from app.schemas.content import Rubric
from app.schemas.extraction import (
    Addressed,
    Backing,
    ClaimType,
    Extraction,
    Verdict,
)
from app.schemas.report import (
    CoverageCounts,
    NarrativeSection,
    PersonaLine,
    RateStats,
    Report,
    ScoredFinding,
    ScoredReport,
)
from app.schemas.scoring import ScoreOutput

_SATISFIED = "satisfied"


class ReactClient(Protocol):
    """The slice of the Bedrock client the narrative needs. A fake satisfies it
    without the network."""

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str: ...


def _row_values(rubric: Rubric) -> dict[str, int]:
    return {row.id: row.support_value for row in rubric.rows}


def _turn_findings(
    turn: Turn,
    extraction: Extraction,
    score: ScoreOutput,
    values: dict[str, int],
) -> list[ScoredFinding]:
    """Emit one finding per span-bearing signal that actually fired this turn.

    Driven by ``matched_rows`` so a finding always maps to a row that moved the
    number (e.g. a backed claim on a red-lined turn is not shown, because the red
    line fired first and suppressed it).
    """
    matched = set(score.matched_rows)
    findings: list[ScoredFinding] = []

    def add(row: str, span: str, detail: str) -> None:
        if row in matched and span.strip():
            findings.append(
                ScoredFinding(
                    turn_index=turn.turn_index,
                    persona_id=turn.persona_id,
                    concern_id=turn.concern_id,
                    rubric_row=row,
                    support_value=values.get(row, 0),
                    span=span,
                    detail=detail,
                )
            )

    for hit in extraction.red_line_hits:
        add("red_line", hit.span, hit.why)
    for dodge in extraction.dodges:
        add("dodge", dodge.evidence, dodge.type.value)
    for claim in extraction.claims:
        if claim.type is ClaimType.commitment and claim.backing is Backing.backed:
            add("evidence_backed", claim.span, claim.text)
    for cov in extraction.sub_question_coverage:
        if cov.addressed in (Addressed.full, Addressed.partial) and cov.span:
            add("approach_cited", cov.span, cov.addressed.value)
    for fc in extraction.fact_checks:
        if fc.verdict is Verdict.refuted:
            add("false_fact", fc.claim, fc.source)

    return findings


def build_scored_report(
    *,
    session_id: uuid.UUID,
    status: str,
    turns: list[Turn],
    meters: list[PersonaMeter],
    concern_statuses: dict[str, str],
    content: Content,
) -> ScoredReport:
    """Render the deterministic, code-owned part of the after-action report."""
    values = _row_values(content.rubric)

    extractions = [Extraction.model_validate(t.extraction_json) for t in turns]
    scores = [ScoreOutput.model_validate(t.score_json) for t in turns]

    coverage = CoverageCounts()
    dodge_types: Counter[str] = Counter()
    contradiction_count = 0
    dodge_count = 0
    findings: list[ScoredFinding] = []

    for turn, extraction, score in zip(turns, extractions, scores, strict=True):
        for cov in extraction.sub_question_coverage:
            if cov.addressed is Addressed.full:
                coverage.full += 1
            elif cov.addressed is Addressed.partial:
                coverage.partial += 1
            else:
                coverage.none += 1
        for dodge in extraction.dodges:
            dodge_types[dodge.type.value] += 1
            dodge_count += 1
        contradiction_count += len(extraction.consistency_flags)
        findings.extend(_turn_findings(turn, extraction, score, values))

    total_turns = len(turns)
    concerns_total = len(concern_statuses)
    concerns_satisfied = sum(1 for s in concern_statuses.values() if s == _SATISFIED)

    rate_stats = RateStats(
        total_turns=total_turns,
        dodge_count=dodge_count,
        dodges_per_turn=round(dodge_count / total_turns, 4) if total_turns else 0.0,
        contradiction_count=contradiction_count,
        concerns_total=concerns_total,
        concerns_satisfied=concerns_satisfied,
        coverage_rate=round(concerns_satisfied / concerns_total, 4) if concerns_total else 0.0,
    )

    return ScoredReport(
        session_id=session_id,
        status=status,
        rate_stats=rate_stats,
        personas=[
            PersonaLine(persona_id=m.persona_id, support=m.support, capped=m.capped)
            for m in meters
        ],
        coverage_counts=coverage,
        # sorted so the JSON is stable regardless of the order dodges appeared in
        dodge_counts_by_type=dict(sorted(dodge_types.items())),
        contradiction_count=contradiction_count,
        findings=findings,
    )


def _narrative_prompt(scored: ScoredReport, content: Content) -> str:
    rs = scored.rate_stats
    meters = ", ".join(
        f"{p.persona_id} {p.support}{' (capped)' if p.capped else ''}" for p in scored.personas
    )
    return "\n\n".join(
        [
            "You are a presentation coach writing a short recap of a federal-orals "
            "rehearsal. This recap is NOT scored: the numbers below were already "
            "computed by code and are final. Do not invent, restate, or assign any "
            "score — describe patterns and give one or two concrete next steps.",
            "## Rehearsal summary (already scored, do not change)",
            "\n".join(
                [
                    f"Concerns satisfied: {rs.concerns_satisfied} of {rs.concerns_total}",
                    f"Coverage rate: {rs.coverage_rate}",
                    f"Dodges: {rs.dodge_count} across {rs.total_turns} turns "
                    f"({rs.dodges_per_turn} per turn)",
                    f"Contradictions: {rs.contradiction_count}",
                    f"Final evaluator support: {meters}",
                ]
            ),
            "## Your task",
            "In 3-4 sentences, tell the presenter what went well, where they lost "
            "ground, and what to drill next time. Plain prose, no headings, no scores.",
        ]
    )


def render_narrative(
    scored: ScoredReport, content: Content, client: ReactClient
) -> NarrativeSection:
    """Produce the single labeled model recap. Reads the scored summary; runs one
    ``react`` call; the text can never move a number because scoring is done."""
    text = client.react(_narrative_prompt(scored, content))
    return NarrativeSection(scored=False, text=text)


def build_report(
    *,
    session_id: uuid.UUID,
    status: str,
    turns: list[Turn],
    meters: list[PersonaMeter],
    concern_statuses: dict[str, str],
    content: Content,
    client: ReactClient,
) -> Report:
    """Build the full report: the deterministic scored part plus the labeled narrative."""
    scored = build_scored_report(
        session_id=session_id,
        status=status,
        turns=turns,
        meters=meters,
        concern_statuses=concern_statuses,
        content=content,
    )
    narrative = render_narrative(scored, content, client)
    return Report(**scored.model_dump(), narrative=narrative)
