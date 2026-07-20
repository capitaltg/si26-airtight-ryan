"""Per-turn code output — produced by the deterministic scoring engine (spec §6).

The model never emits these. Pure Python owns ``support_delta``,
``matched_rows``, and ``capped``.
"""

from pydantic import BaseModel, Field


class ScoreOutput(BaseModel):
    support_delta: int = Field(ge=-2, le=2)
    matched_rows: list[str] = Field(default_factory=list)
    capped: bool = False
