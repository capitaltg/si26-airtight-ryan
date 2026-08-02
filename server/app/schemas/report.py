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
    """Sub-question coverage tallied across every turn's extraction."""

    full: int = 0
    partial: int = 0
    none: int = 0


class RateStats(BaseModel):
    """Length-independent headline stats — these lead the report so a short strong
    rehearsal isn't punished against a long rambling one."""

    total_turns: int
    dodge_count: int
    dodges_per_turn: float
    contradiction_count: int
    concerns_total: int
    concerns_satisfied: int
    coverage_rate: float  # concerns_satisfied / concerns_total


class FindingEvidence(BaseModel):
    """One verbatim quote that fed a row application, with its per-quote detail."""

    span: str = Field(min_length=1)
    detail: str


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


class Report(ScoredReport):
    """The full report: the scored part plus the labeled model narrative."""

    narrative: NarrativeSection
