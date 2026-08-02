"""The deterministic scoring engine — the moat (spec §6).

Pure functions, no I/O, no model. Code owns ``support_delta``, ``matched_rows``,
and ``capped``. Any path that lets a model set the number is a defect.

Combination rule
----------------
A crossed red line fires first: it forces the cap and ``support_delta = -2`` and
ignores every other row. Otherwise the matching rows are summed and clamped to
[-2, +2]:

- ``dodge`` (-2)          — any dodge present
- ``false_fact`` (-1)     — once per refuted tier-1+ fact_check (accumulates before
  clamp); tier-0 refutations are contradictions, not false facts
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
from app.schemas.scoring import LimitMeasurement, LimitResult, ScoreOutput

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
    "over_limit",
]


def score_turn(extraction: Extraction, rubric: Rubric) -> ScoreOutput:
    """Score a single turn from its validated extraction. Pure, deterministic."""
    values = {row.id: row.support_value for row in rubric.rows}

    # Red line fires first and forces the cap, ignoring other semantic rows.
    if extraction.red_line_hits:
        return ScoreOutput(
            support_delta=values["red_line"],
            raw_support_delta=values["red_line"],
            matched_rows=["red_line"],
            row_counts={"red_line": 1},
            capped=True,
        )

    delta = 0
    counts: dict[str, int] = {}

    if extraction.dodges:
        counts["dodge"] = 1
        delta += values["dodge"]

    # Tier 0 is a conflict with an earlier answer, which the `contradiction` row
    # already charges. The model mirrors such a conflict into fact_checks as well
    # as consistency_flags, so counting tier 0 here bills one statement twice.
    # Only a document refutation (tier 1+) is a false fact.
    refuted = sum(
        1 for fc in extraction.fact_checks if fc.verdict is Verdict.refuted and fc.tier >= 1
    )
    if refuted:
        counts["false_fact"] = refuted
        delta += values["false_fact"] * refuted

    if extraction.consistency_flags:
        counts["contradiction"] = 1
        delta += values["contradiction"]

    backed = any(
        claim.type is ClaimType.commitment and claim.backing is Backing.backed
        for claim in extraction.claims
    )
    if backed:
        counts["evidence_backed"] = 1
        delta += values["evidence_backed"]

    cited = any(
        cov.addressed in (Addressed.full, Addressed.partial)
        for cov in extraction.sub_question_coverage
    )
    # approach_cited is the weaker positive; a backed commitment already captures
    # the credit, so don't double-count.
    if cited and not backed:
        counts["approach_cited"] = 1
        delta += values["approach_cited"]

    if not counts:
        counts["unsubstantiated"] = 1
        delta += values["unsubstantiated"]  # 0

    raw = delta
    delta = max(-2, min(2, raw))
    ordered = [row for row in _ROW_ORDER if row in counts]
    return ScoreOutput(
        support_delta=delta,
        raw_support_delta=raw,
        matched_rows=ordered,
        row_counts={row: counts[row] for row in ordered},
        capped=False,
    )


def apply_limit_penalty(
    score: ScoreOutput, rubric: Rubric, limit: LimitMeasurement
) -> ScoreOutput:
    """Apply one objective limit adjustment after the evaluator reaction.

    ``score`` is the semantic result already shown to the model. This pure
    function owns the later adjustment; the model neither sees nor computes it.
    """
    values = {row.id: row.support_value for row in rubric.rows}
    exceeded = limit.measured > limit.limit_threshold
    penalty = values["over_limit"] if exceeded else 0
    result = LimitResult(
        **limit.model_dump(),
        exceeded=exceeded,
        penalty_applied=exceeded,
        penalty_value=penalty,
    )
    if not exceeded:
        return score.model_copy(update={"limit": result})

    counts = {**score.row_counts, "over_limit": 1}
    ordered = [row for row in _ROW_ORDER if row in counts]
    return ScoreOutput(
        support_delta=score.support_delta + penalty,
        raw_support_delta=score.raw_support_delta,
        matched_rows=ordered,
        row_counts={row: counts[row] for row in ordered},
        capped=score.capped,
        limit=result,
    )


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
