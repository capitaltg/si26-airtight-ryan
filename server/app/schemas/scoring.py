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
    matched_rows: list[str] = Field(default_factory=list)
    capped: bool = False
    limit: LimitResult | None = None
