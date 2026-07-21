"""The deterministic scoring engine — the moat (spec §6).

Pure functions, no I/O, no model. Code owns ``support_delta``, ``matched_rows``,
and ``capped``. Any path that lets a model set the number is a defect.

Combination rule
----------------
A crossed red line fires first: it forces the cap and ``support_delta = -2`` and
ignores every other row. Otherwise the matching rows are summed and clamped to
[-2, +2]:

- ``dodge`` (-2)          — any dodge present
- ``false_fact`` (-1)     — once per refuted fact_check (accumulates before clamp)
- ``contradiction`` (-1)  — any consistency flag (Tier-0 conflict)
- ``evidence_backed`` (+2) — any commitment claim with ``backing == backed``
- ``approach_cited`` (+1) — coverage full/partial, and not already evidence_backed
- ``unsubstantiated`` (0) — fallback when nothing else matched, so matched_rows is
  never empty and the audit trail always names a row.
"""

from app.schemas.content import Rubric
from app.schemas.extraction import (
    Addressed,
    Backing,
    ClaimType,
    Extraction,
    Verdict,
)
from app.schemas.scoring import ScoreOutput

# Canonical row order for matched_rows output. Mirrors rubric.yaml so the audit
# trail is stable regardless of which signals fired.
_ROW_ORDER = [
    "red_line",
    "dodge",
    "unsubstantiated",
    "false_fact",
    "contradiction",
    "approach_cited",
    "evidence_backed",
]


def score_turn(extraction: Extraction, rubric: Rubric) -> ScoreOutput:
    """Score a single turn from its validated extraction. Pure, deterministic."""
    values = {row.id: row.support_value for row in rubric.rows}

    # Red line fires first and forces the cap, ignoring all other rows.
    if extraction.red_line_hits:
        return ScoreOutput(
            support_delta=values["red_line"],
            matched_rows=["red_line"],
            capped=True,
        )

    delta = 0
    matched: set[str] = set()

    if extraction.dodges:
        matched.add("dodge")
        delta += values["dodge"]

    refuted = sum(1 for fc in extraction.fact_checks if fc.verdict is Verdict.refuted)
    if refuted:
        matched.add("false_fact")
        delta += values["false_fact"] * refuted

    if extraction.consistency_flags:
        matched.add("contradiction")
        delta += values["contradiction"]

    backed = any(
        claim.type is ClaimType.commitment and claim.backing is Backing.backed
        for claim in extraction.claims
    )
    if backed:
        matched.add("evidence_backed")
        delta += values["evidence_backed"]

    cited = any(
        cov.addressed in (Addressed.full, Addressed.partial)
        for cov in extraction.sub_question_coverage
    )
    # approach_cited is the weaker positive; a backed commitment already captures
    # the credit, so don't double-count.
    if cited and not backed:
        matched.add("approach_cited")
        delta += values["approach_cited"]

    if not matched:
        matched.add("unsubstantiated")
        delta += values["unsubstantiated"]  # 0

    delta = max(-2, min(2, delta))
    ordered = [row for row in _ROW_ORDER if row in matched]
    return ScoreOutput(support_delta=delta, matched_rows=ordered, capped=False)


def apply_to_meter(
    current: int,
    delta: int,
    capped: bool,
    cap_ceiling: int,
    already_capped: bool,
) -> tuple[int, bool]:
    """Apply a turn's delta to a persona's meter.

    Clamp to [0, 100], then — if this persona has ever crossed a red line
    (``already_capped`` sticky, or ``capped`` this turn) — hold the meter at
    ``min(meter, cap_ceiling)``. Returns ``(new_meter, sticky_capped)``.
    """
    new = max(0, min(100, current + delta))
    sticky = already_capped or capped
    if sticky:
        new = min(new, cap_ceiling)
    return new, sticky
