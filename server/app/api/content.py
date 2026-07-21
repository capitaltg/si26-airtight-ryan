"""Content API — the disclosed rubric panel (spec: rubric is shown, not hidden).

Serves the scoring rubric and each concern's expectations so the UI can render
"How you're scored" (task 11). Read-only; sources straight from the authored
content loaded at startup.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_content
from app.content.loader import Content
from app.schemas.content import RubricRow

router = APIRouter(prefix="/content", tags=["content"])


class ConcernDisclosureDTO(BaseModel):
    concern_id: str
    core_ask: str
    what_would_satisfy: str
    red_lines: list[str]


class RubricDisclosureDTO(BaseModel):
    version: int
    cap_ceiling: int
    rows: list[RubricRow]
    concerns: list[ConcernDisclosureDTO]


@router.get("/rubric", response_model=RubricDisclosureDTO)
def get_rubric(content: Content = Depends(get_content)) -> RubricDisclosureDTO:
    return RubricDisclosureDTO(
        version=content.rubric.version,
        cap_ceiling=content.rubric.cap_ceiling,
        rows=content.rubric.rows,
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
