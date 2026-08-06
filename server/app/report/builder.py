"""After-action report builder (task 12).

The scored part is rendered entirely in code from the stored turns — no model
touches a number here. ``build_scored_report`` is pure and deterministic:
regenerating it from the same turns is byte-identical. The single model call
lives in ``render_narrative``, which produces a coaching recap tagged
``scored=False``; it reads the already-computed summary and never sets a score.

Findings vs counts
------------------
A ``ScoredFinding`` must carry a verbatim span, so it is emitted only for the
signals that carry one: ``red_line`` (hit span, countered by the authored rule
text behind its validated ``source_id``), ``dodge`` (``answer_span``),
``contradiction`` (``current_answer_span``, countered by the prior turn's
``prior_answer_span``), ``evidence_backed`` (the backed claim's span),
``approach_cited`` (coverage span), and ``false_fact`` (``answer_span``,
countered by the document's ``source_quote``). ``unsubstantiated`` has no
verbatim span in the extraction schema, so it alone is surfaced as a count
instead — never as a spanless "scored line".
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from typing import Protocol

from app.content.loader import Content
from app.db.models import Clarification, PersonaMeter, Turn
from app.pipeline.scoring import apply_limit_penalty, score_turn
from app.schemas.content import NonNegotiable, RedLine, Rubric
from app.schemas.extraction import (
    Addressed,
    Backing,
    ClaimType,
    Extraction,
    RedLineHit,
    RedLineSourceKind,
    Verdict,
)
from app.schemas.report import (
    ClarificationLine,
    CoverageCounts,
    FindingEvidence,
    LimitFinding,
    NarrativeSection,
    PersonaLine,
    RateStats,
    Report,
    ScoredFinding,
    ScoredReport,
    TurnScoreAudit,
)
from app.schemas.scoring import LimitMeasurement, ScoreOutput

logger = logging.getLogger(__name__)

_SATISFIED = "satisfied"

# The four terminal concern states (`app.pipeline.orchestrator`), best outcome
# first so the breakdown reads the same way in every report. Spelled out here
# rather than imported: the report renders statuses read off stored rows, and an
# archived session can carry a value this build would never write.
_TERMINAL_ORDER = ("satisfied", "partial_exhausted", "dodged", "breached")

# How each state is named to the coaching model. Prose, not identifiers, because
# the narrative is written for the presenter.
_STATUS_LABELS = {
    "satisfied": "satisfied",
    "partial_exhausted": "partial (attempts used)",
    "dodged": "dodged",
    "breached": "red line crossed",
}


def _status_counts(concern_statuses: dict[str, str]) -> dict[str, int]:
    """Every concern's final state, counted once.

    The four terminal states are always present, zeros included, so the report's
    shape does not depend on how the rehearsal went. Anything else — ``open`` or
    ``partial`` from a session ended early, or a value written before the terminal
    states split — is appended in sorted order rather than dropped, so the counts
    always sum to ``concerns_total``.
    """
    counts = Counter(concern_statuses.values())
    ordered = {status: counts[status] for status in _TERMINAL_ORDER}
    ordered.update(
        {status: n for status, n in sorted(counts.items()) if status not in _TERMINAL_ORDER}
    )
    return ordered


def _outcome_line(rate_stats: RateStats) -> str:
    """The non-satisfied outcomes, named, for the narrative prompt. ``"none"``
    when there are none, so the model is never handed a dangling label."""
    parts = [
        f"{_STATUS_LABELS.get(status, status)} {count}"
        for status, count in rate_stats.concerns_by_status.items()
        if status != _SATISFIED and count
    ]
    return ", ".join(parts) or "none"


class ReactClient(Protocol):
    """The slice of the Bedrock client the narrative needs. A fake satisfies it
    without the network."""

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str: ...


def _row_values(rubric: Rubric) -> dict[str, int]:
    return {row.id: row.support_value for row in rubric.rows}


def _authored_rule(
    hit: RedLineHit, content: Content, concern_id: str, persona_id: str
) -> str | None:
    """The authored text behind a validated ``source_id``.

    Resolved in code rather than quoted by the model: grounding has already
    proven the id is authored against this turn's own concern or persona, so
    the text is a lookup and a fabricated rule reference is structurally
    impossible.

    The ``non_negotiable`` lookup is scoped to the turn's own persona rather
    than searched across every persona: ``slug_id`` only dedupes ids within
    one persona, so two personas can share a non-negotiable id, and searching
    all of them could return the wrong persona's rule text for a hit that
    grounding already validated against exactly this turn's persona.
    """
    rules: list[RedLine] | list[NonNegotiable]
    if hit.source_kind is RedLineSourceKind.concern_red_line:
        concern = content.concerns.get(concern_id)
        rules = concern.red_lines if concern is not None else []
    else:
        persona = content.personas.get(persona_id)
        rules = persona.non_negotiables if persona is not None else []
    return next((rule.text for rule in rules if rule.id == hit.source_id), None)


def _turn_findings(
    turn: Turn,
    extraction: Extraction,
    score: ScoreOutput,
    values: dict[str, int],
    content: Content,
) -> list[ScoredFinding]:
    """Emit one grouped finding per charged row, with both sides of its evidence.

    Driven by ``matched_rows`` so a finding always maps to a row that moved the
    number. Every span here was verified by ``drop_ungrounded`` against a real
    source, so no row can print an unverifiable quote.
    """
    matched = set(score.matched_rows)
    evidence: dict[str, list[FindingEvidence]] = {}

    def add(
        row: str,
        span: str,
        detail: str,
        counter_span: str | None = None,
        counter_label: str | None = None,
    ) -> None:
        if row in matched and span.strip():
            evidence.setdefault(row, []).append(
                FindingEvidence(
                    span=span,
                    detail=detail,
                    counter_span=counter_span,
                    counter_label=counter_label,
                )
            )

    for hit in extraction.red_line_hits:
        add(
            "red_line",
            hit.span,
            hit.why,
            _authored_rule(hit, content, turn.concern_id, turn.persona_id),
            f"{hit.source_kind.value}: {hit.source_id}",
        )
    for dodge in extraction.dodges:
        add("dodge", dodge.answer_span, dodge.explanation or dodge.type.value)
    for flag in extraction.consistency_flags:
        detail = flag.explanation or "conflicts with an earlier answer"
        if flag.acknowledged_revision:
            detail = f"{detail} (presenter acknowledged the revision)"
        add(
            "contradiction",
            flag.current_answer_span,
            detail,
            flag.prior_answer_span,
            f"turn {flag.conflicts_with_turn + 1}",
        )
    for claim in extraction.claims:
        if claim.type is ClaimType.commitment and claim.backing is Backing.backed:
            add("evidence_backed", claim.span, claim.text)
    for cov in extraction.sub_question_coverage:
        if cov.addressed in (Addressed.full, Addressed.partial) and cov.span:
            add("approach_cited", cov.span, cov.addressed.value)
    for fc in extraction.fact_checks:
        if fc.verdict is Verdict.refuted and fc.tier >= 1:
            add(
                "false_fact",
                fc.answer_span,
                fc.claim,
                fc.source_quote,
                fc.source_document_id.value,
            )

    return [
        ScoredFinding(
            turn_index=turn.turn_index,
            persona_id=turn.persona_id,
            concern_id=turn.concern_id,
            rubric_row=row,
            support_value=values.get(row, 0),
            count=score.row_counts.get(row, 1),
            evidence=evidence[row],
        )
        for row in score.matched_rows
        if row in evidence
    ]


def _audit_turn(
    turn: Turn, extraction: Extraction, persisted: ScoreOutput, rubric: Rubric
) -> TurnScoreAudit:
    """Re-derive this turn's number from the extraction stored beside it.

    Runs the same pure path the live turn ran: ``score_turn`` for the semantic
    rows, then ``apply_limit_penalty`` when the turn recorded a limit
    measurement. Row combination, the clamp, and the limit penalty are therefore
    all exercised again against the evidence the report prints.
    """
    recomputed = score_turn(extraction, rubric)
    if persisted.limit is not None:
        recomputed = apply_limit_penalty(
            recomputed,
            rubric,
            LimitMeasurement(
                kind=persisted.limit.kind,
                measured=persisted.limit.measured,
                warning_threshold=persisted.limit.warning_threshold,
                limit_threshold=persisted.limit.limit_threshold,
            ),
        )
    agrees = (
        recomputed.support_delta == persisted.support_delta
        and recomputed.matched_rows == persisted.matched_rows
    )
    if not agrees:
        logger.warning(
            "score audit disagrees on turn %s: persisted %+d %s, recomputed %+d %s",
            turn.turn_index,
            persisted.support_delta,
            persisted.matched_rows,
            recomputed.support_delta,
            recomputed.matched_rows,
        )
    return TurnScoreAudit(
        turn_index=turn.turn_index,
        persisted_support_delta=persisted.support_delta,
        recomputed_support_delta=recomputed.support_delta,
        persisted_matched_rows=list(persisted.matched_rows),
        recomputed_matched_rows=list(recomputed.matched_rows),
        agrees=agrees,
    )


def build_scored_report(
    *,
    session_id: uuid.UUID,
    status: str,
    turns: list[Turn],
    meters: list[PersonaMeter],
    concern_statuses: dict[str, str],
    content: Content,
    clarifications: list[Clarification] | None = None,
) -> ScoredReport:
    """Render the deterministic, code-owned part of the after-action report.

    ``clarifications`` are purely additive: they are non-scored exchanges shown
    for auditability and never touch any stat above.
    """
    values = _row_values(content.rubric)

    extractions = [Extraction.model_validate(t.extraction_json) for t in turns]
    scores = [ScoreOutput.model_validate(t.score_json) for t in turns]

    coverage = CoverageCounts()
    dodge_types: Counter[str] = Counter()
    contradiction_count = 0
    dodge_count = 0
    findings: list[ScoredFinding] = []
    limit_findings: list[LimitFinding] = []
    audits: list[TurnScoreAudit] = []

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
        findings.extend(_turn_findings(turn, extraction, score, values, content))
        audits.append(_audit_turn(turn, extraction, score, content.rubric))
        if score.limit is not None and score.limit.penalty_applied:
            limit_findings.append(
                LimitFinding(
                    turn_index=turn.turn_index,
                    persona_id=turn.persona_id,
                    concern_id=turn.concern_id,
                    kind=score.limit.kind,
                    measured=score.limit.measured,
                    limit_threshold=score.limit.limit_threshold,
                    penalty=score.limit.penalty_value,
                )
            )

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
        concerns_by_status=_status_counts(concern_statuses),
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
        limit_findings=limit_findings,
        score_audit=audits,
        score_audit_agrees=all(a.agrees for a in audits),
        clarifications=[
            ClarificationLine(
                persona_id=c.persona_id,
                concern_id=c.concern_id,
                question=c.question,
                reply=c.reply,
            )
            for c in (clarifications or [])
        ],
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
            "score. Describe patterns and give one or two concrete next steps.",
            "## Rehearsal summary (already scored, do not change)",
            "\n".join(
                [
                    f"Concerns satisfied: {rs.concerns_satisfied} of {rs.concerns_total}",
                    f"Other outcomes: {_outcome_line(rs)}",
                    f"Coverage rate: {rs.coverage_rate}",
                    f"Dodges: {rs.dodge_count} across {rs.total_turns} turns "
                    f"({rs.dodges_per_turn} per turn)",
                    f"Contradictions: {rs.contradiction_count}",
                    f"Final evaluator support: {meters}",
                ]
            ),
            "A completed session means every concern used up its attempts. It does not "
            "mean the rubric was met. A concern listed under other outcomes was not "
            "satisfied, and a red line crossed is a breach, not an omission.",
            "## Your task",
            "In 3 or 4 sentences, tell the presenter how the rehearsal went and what "
            "to work on next. Write like a person talking to them: plain prose, short "
            "sentences, no headings, no scores. Do not describe the rehearsal as "
            "successful on the strength of it finishing. Do not use em dashes, and do "
            "not force the recap into a three-part list or lean on promotional "
            "adjectives.",
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
    clarifications: list[Clarification] | None = None,
) -> Report:
    """Build the full report: the deterministic scored part plus the labeled narrative."""
    scored = build_scored_report(
        session_id=session_id,
        status=status,
        turns=turns,
        meters=meters,
        concern_statuses=concern_statuses,
        content=content,
        clarifications=clarifications,
    )
    narrative = render_narrative(scored, content, client)
    return Report(**scored.model_dump(), narrative=narrative)
