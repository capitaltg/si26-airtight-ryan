"""Per-turn code output — produced by the deterministic scoring engine (spec §6).

The model never emits these. Pure Python owns ``support_delta``,
``matched_rows``, and ``capped``.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class LimitKind(StrEnum):
    text_words = "text_words"
    voice_seconds = "voice_seconds"


class LimitMeasurement(BaseModel):
    kind: LimitKind
    measured: float = Field(ge=0)
    warning_threshold: float = Field(gt=0)
    limit_threshold: float = Field(gt=0)

    @model_validator(mode="after")
    def _warning_precedes_limit(self) -> "LimitMeasurement":
        if self.warning_threshold >= self.limit_threshold:
            raise ValueError("warning_threshold must be less than limit_threshold")
        return self


class LimitResult(LimitMeasurement):
    exceeded: bool
    penalty_applied: bool
    penalty_value: int


class ScoreOutput(BaseModel):
    # Semantic scoring remains [-2, +2]. A separate post-reaction over-limit
    # penalty can take the final persisted turn delta to -3.
    support_delta: int = Field(ge=-3, le=2)
    raw_support_delta: int = 0
    matched_rows: list[str] = Field(default_factory=list)
    row_counts: dict[str, int] = Field(default_factory=dict)
    capped: bool = False
    # A ceiling row (false_fact, contradiction) held this turn's delta down.
    # Deliberately NOT `capped`: that one is read by `apply_to_meter` to pin the
    # persona's meter at 25 for the rest of the session, which a false fact must
    # not do. Defaults False so archived score_json still validates.
    integrity_ceiling: bool = False
    limit: LimitResult | None = None

    @model_validator(mode="after")
    def _backfill_legibility_fields(self) -> "ScoreOutput":
        counts = {row: self.row_counts.get(row, 1) for row in self.matched_rows}
        if counts != self.row_counts:
            self.row_counts = counts
        if self.raw_support_delta == 0:
            penalty = (
                self.limit.penalty_value
                if self.limit is not None and self.limit.penalty_applied
                else 0
            )
            self.raw_support_delta = self.support_delta - penalty
        return self
