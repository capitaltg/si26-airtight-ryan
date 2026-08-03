"""Read the fixed evaluator personas for the content editor."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_content
from app.content import persona_writer
from app.content.loader import Content
from app.pipeline.orchestrator import PERSONA_ORDER
from app.schemas.content import Exemplar, PersonaDefinition

router = APIRouter(prefix="/content/personas", tags=["personas"])


class PersonaDTO(BaseModel):
    """Full persona definition plus its shipped-default comparison result."""

    id: str
    display_name: str
    intro: str
    voice: str
    demographics: str
    values: list[str]
    wants: list[str]
    priorities: list[str]
    non_negotiables: list[str]
    rubric_version: int
    polly_voice_id: str
    exemplars: list[Exemplar]
    is_customized: bool


def _to_dto(persona: PersonaDefinition) -> PersonaDTO:
    return PersonaDTO(
        **persona.model_dump(),
        is_customized=persona_writer.is_customized(persona.id),
    )


@router.get("", response_model=list[PersonaDTO])
def list_personas(content: Content = Depends(get_content)) -> list[PersonaDTO]:
    """Return the shipped evaluators in their fixed rehearsal turn order."""
    rank = {persona_id: index for index, persona_id in enumerate(PERSONA_ORDER)}
    ordered = sorted(
        content.personas.values(), key=lambda persona: (rank.get(persona.id, len(rank)), persona.id)
    )
    return [_to_dto(persona) for persona in ordered]
