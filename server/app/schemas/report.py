"""After-action report schema (spec §8, task 12).

The scored part is code-rendered from stored turns and is fully deterministic —
regenerating it from the same turns is byte-identical. ``ScoredFinding`` ties a
verbatim span to the rubric row it fired, so every scored line in the report is
auditable. The model narrative is a separate section, tagged ``scored=False``,
and never carries or sets a number.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.scoring import LimitKind


class PersonaLine(BaseModel):
    """A persona's final support and whether a red line pinned it."""

    persona_id: str
    support: int
    capped: bool


class CoverageCounts(BaseModel):
    """Sub-question coverage, each authored sub-question counted once.

    One row per sub-question of every concern on the agenda, at its best outcome
    across that concern's attempts — so ``full + partial + none`` is the number of
    sub-questions the rehearsal had to cover, and a concern that took its
    follow-up does not contribute its sub-questions twice.
    """

    full: int = 0
    partial: int = 0
    none: int = 0


class RateStats(BaseModel):
    """Length-independent headline stats — these lead the report so a short strong
    rehearsal isn't punished against a long rambling one.

    ``concerns_satisfied`` is the strict count of the ``satisfied`` terminal state.
    A concern that ran out of follow-ups on partial coverage, was dodged, or
    crossed a red line is not in it — it is in ``concerns_by_status``, which
    accounts for every concern exactly once. ``concerns_by_status`` defaults to
    empty so a report stored before the terminal states split still validates.
    """

    total_turns: int
    dodge_count: int
    dodges_per_turn: float
    contradiction_count: int
    concerns_total: int
    concerns_satisfied: int
    coverage_rate: float  # concerns_satisfied / concerns_total
    concerns_by_status: dict[str, int] = Field(default_factory=dict)


class FindingEvidence(BaseModel):
    """One verbatim quote that fed a row application, with its per-quote detail.

    ``counter_span`` is the other side of the relationship the row charges: the
    prior answer for a contradiction, the document quote for a false fact, the
    authored rule for a red line. ``None`` for rows that assert nothing about a
    second text.
    """

    span: str = Field(min_length=1)
    detail: str
    counter_span: str | None = None
    counter_label: str | None = None


class ScoredFinding(BaseModel):
    """One charged row on one turn, with every verbatim quote behind it."""

    turn_index: int
    persona_id: str
    concern_id: str
    rubric_row: str
    support_value: int  # per application
    count: int = Field(default=1, ge=1)
    evidence: list[FindingEvidence] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_span(cls, data: Any) -> Any:
        if isinstance(data, dict) and "evidence" not in data and "span" in data:
            data = dict(data)
            data["evidence"] = [{"span": data["span"], "detail": data.get("detail", "")}]
            data.setdefault("count", 1)
        return data


class ClarificationLine(BaseModel):
    """One non-scored clarification exchange, surfaced in the report so overuse is
    auditable. It never carries a support value: a clarification does not score."""

    persona_id: str
    concern_id: str
    question: str
    reply: str


class LimitFinding(BaseModel):
    turn_index: int
    persona_id: str
    concern_id: str
    kind: LimitKind
    measured: float
    limit_threshold: float
    penalty: int


class NarrativeSection(BaseModel):
    """The one model-authored recap. Explicitly not scored; it never feeds a number."""

    scored: bool = False
    header: str = "Not scored"
    text: str


class TurnScoreAudit(BaseModel):
    """An independent recomputation of one turn's number from its stored evidence.

    The report renders the disagreement rather than hiding it: the persisted value
    is never rewritten from here.
    """

    turn_index: int
    persisted_support_delta: int
    recomputed_support_delta: int
    persisted_matched_rows: list[str]
    recomputed_matched_rows: list[str]
    agrees: bool


class ScoredReport(BaseModel):
    """The deterministic, code-rendered part of the after-action report."""

    session_id: uuid.UUID
    status: str
    rate_stats: RateStats
    personas: list[PersonaLine] = Field(default_factory=list)
    coverage_counts: CoverageCounts
    dodge_counts_by_type: dict[str, int] = Field(default_factory=dict)
    contradiction_count: int
    findings: list[ScoredFinding] = Field(default_factory=list)
    limit_findings: list[LimitFinding] = Field(default_factory=list)
    clarifications: list[ClarificationLine] = Field(default_factory=list)
    score_audit: list[TurnScoreAudit] = Field(default_factory=list)
    score_audit_agrees: bool = True


class Report(ScoredReport):
    """The full report: the scored part plus the labeled model narrative."""

    narrative: NarrativeSection
