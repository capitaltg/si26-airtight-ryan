"""Read the fixed evaluator personas for the content editor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.api.deps import get_content, reload_content
from app.content import persona_writer
from app.content.loader import Content
from app.pipeline.orchestrator import PERSONA_ORDER
from app.schemas.content import Exemplar, PersonaDefinition, PersonaUpdate

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


def _require_known(content: Content, persona_id: str) -> None:
    if persona_id not in content.personas:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")


def _field_errors(exc: ValidationError) -> list[dict[str, object]]:
    """Reshape a merge-time ValidationError into FastAPI's own 422 body.

    Prefixing the error location with ``body`` makes merge failures match
    FastAPI request-validation failures for the editor.
    """
    return [
        {"loc": ["body", *error["loc"]], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]


@router.get("", response_model=list[PersonaDTO])
def list_personas(content: Content = Depends(get_content)) -> list[PersonaDTO]:
    """Return the shipped evaluators in their fixed rehearsal turn order."""
    rank = {persona_id: index for index, persona_id in enumerate(PERSONA_ORDER)}
    ordered = sorted(
        content.personas.values(), key=lambda persona: (rank.get(persona.id, len(rank)), persona.id)
    )
    return [_to_dto(persona) for persona in ordered]


@router.put("/{persona_id}", response_model=PersonaDTO)
def update_persona(
    persona_id: str,
    update: PersonaUpdate,
    request: Request,
    content: Content = Depends(get_content),
) -> PersonaDTO:
    _require_known(content, persona_id)
    try:
        persona = persona_writer.save_persona(persona_id, update)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_field_errors(exc)) from exc
    reload_content(request.app)
    return _to_dto(persona)


@router.post("/{persona_id}/reset", response_model=PersonaDTO)
def reset_persona(
    persona_id: str,
    request: Request,
    content: Content = Depends(get_content),
) -> PersonaDTO:
    _require_known(content, persona_id)
    persona = persona_writer.reset_persona(persona_id)
    reload_content(request.app)
    return _to_dto(persona)
