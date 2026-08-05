"""Content API — the disclosed rubric panel (spec: rubric is shown, not hidden).

Serves the scoring rubric and each concern's expectations so the UI can render
"How you're scored" (task 11). Read-only; sources straight from the authored
content loaded at startup.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_content
from app.config import settings
from app.content.loader import Content
from app.schemas.content import RedLine, RubricRow

router = APIRouter(prefix="/content", tags=["content"])


class ConcernDisclosureDTO(BaseModel):
    concern_id: str
    core_ask: str
    what_would_satisfy: str
    red_lines: list[RedLine]


class RubricDisclosureDTO(BaseModel):
    version: int
    rows: list[RubricRow]
    combination: list[str]
    concerns: list[ConcernDisclosureDTO]


class TangentLimitDTO(BaseModel):
    warning: float
    limit: float
    unit: str


class TangentLimitsDTO(BaseModel):
    text: TangentLimitDTO
    voice: TangentLimitDTO
    penalty: int


@router.get("/rubric", response_model=RubricDisclosureDTO)
def get_rubric(content: Content = Depends(get_content)) -> RubricDisclosureDTO:
    return RubricDisclosureDTO(
        version=content.rubric.version,
        rows=content.rubric.rows,
        combination=content.rubric.combination,
        concerns=[
            ConcernDisclosureDTO(
                concern_id=c.concern_id,
                core_ask=c.core_ask,
                what_would_satisfy=c.what_would_satisfy,
                red_lines=c.red_lines,
            )
            for c in content.concerns.values()
        ],
    )


@router.get("/tangent-limits", response_model=TangentLimitsDTO)
def get_tangent_limits(content: Content = Depends(get_content)) -> TangentLimitsDTO:
    row = next((row for row in content.rubric.rows if row.id == "over_limit"), None)
    if row is None:
        raise RuntimeError("rubric is missing required over_limit row")
    return TangentLimitsDTO(
        text=TangentLimitDTO(
            warning=settings.text_answer_warning_words,
            limit=settings.text_answer_limit_words,
            unit="words",
        ),
        voice=TangentLimitDTO(
            warning=settings.voice_answer_warning_seconds,
            limit=settings.voice_answer_limit_seconds,
            unit="seconds",
        ),
        penalty=row.support_value,
    )
