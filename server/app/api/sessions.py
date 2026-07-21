"""Session API — create a rehearsal, submit answers, end, and read the report.

The router is a thin HTTP shell over the code-driven orchestrator: it never
scores or selects concerns itself. DTOs here are the contract the frontend
mirrors in ``types.ts`` (task 11).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_bedrock_client, get_content, get_db
from app.bedrock.client import BedrockClient
from app.content.loader import Content
from app.db import repo
from app.db.models import RehearsalSession
from app.pipeline import orchestrator
from app.pipeline.orchestrator import SessionComplete
from app.report.builder import build_report
from app.schemas.report import Report

router = APIRouter(prefix="/sessions", tags=["sessions"])


class MeterDTO(BaseModel):
    persona_id: str
    support: int
    capped: bool


class PromptDTO(BaseModel):
    persona_id: str
    concern_id: str
    prompt: str
    is_follow_up: bool


class SessionStateDTO(BaseModel):
    id: uuid.UUID
    status: str
    persona_ids: list[str]
    meters: list[MeterDTO]
    concern_status: dict[str, str]
    prompt: PromptDTO | None  # None once the session is complete
    done: bool


class AnswerRequest(BaseModel):
    answer: str


class AnswerResponse(BaseModel):
    reply: str
    rationale: str
    persona_id: str
    concern_id: str
    concern_status: str
    support_delta: int
    matched_rows: list[str]
    meter: int
    capped: bool
    meters: list[MeterDTO]
    next_prompt: PromptDTO | None
    done: bool


def _meters(db: Session, session_id: uuid.UUID) -> list[MeterDTO]:
    return [
        MeterDTO(persona_id=m.persona_id, support=m.support, capped=m.capped)
        for m in repo.get_meters(db, session_id)
    ]


def _prompt_dto(asg: orchestrator.Assignment | None) -> PromptDTO | None:
    if asg is None:
        return None
    return PromptDTO(
        persona_id=asg.persona.id,
        concern_id=asg.concern.concern_id,
        prompt=asg.prompt,
        is_follow_up=asg.is_follow_up,
    )


def _state(db: Session, content: Content, session: RehearsalSession) -> SessionStateDTO:
    asg = orchestrator.next_concern(db, content, session)
    return SessionStateDTO(
        id=session.id,
        status=session.status,
        persona_ids=list(session.persona_ids),
        meters=_meters(db, session.id),
        concern_status=repo.get_concern_statuses(db, session.id),
        prompt=_prompt_dto(asg),
        done=asg is None,
    )


def _require_session(db: Session, session_id: uuid.UUID) -> RehearsalSession:
    session = repo.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("", response_model=SessionStateDTO, status_code=201)
def create_session(
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
) -> SessionStateDTO:
    session = orchestrator.start_session(db, content)
    return _state(db, content, session)


@router.get("/{session_id}", response_model=SessionStateDTO)
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
) -> SessionStateDTO:
    return _state(db, content, _require_session(db, session_id))


@router.post("/{session_id}/answer", response_model=AnswerResponse)
def submit_answer(
    session_id: uuid.UUID,
    body: AnswerRequest,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
    client: BedrockClient = Depends(get_bedrock_client),
) -> AnswerResponse:
    session = _require_session(db, session_id)
    try:
        result = orchestrator.submit_answer(db, content, client, session, body.answer)
    except SessionComplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AnswerResponse(
        reply=result.reaction.in_character_reply,
        rationale=result.reaction.rationale,
        persona_id=result.persona_id,
        concern_id=result.concern_id,
        concern_status=result.concern_status,
        support_delta=result.support_delta,
        matched_rows=result.matched_rows,
        meter=result.meter,
        capped=result.capped,
        meters=_meters(db, session.id),
        next_prompt=_prompt_dto(result.next),
        done=result.done,
    )


@router.post("/{session_id}/end", response_model=SessionStateDTO)
def end_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
) -> SessionStateDTO:
    session = _require_session(db, session_id)
    session.status = "ended"
    db.flush()
    return _state(db, content, session)


@router.get("/{session_id}/report", response_model=Report)
def get_report(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
    client: BedrockClient = Depends(get_bedrock_client),
) -> Report:
    """The after-action report: a 100% code-rendered scored part (rate stats,
    per-persona meters, coverage/dodge/contradiction counts, and every finding's
    verbatim span) plus one labeled 'Not scored' model narrative."""
    session = _require_session(db, session_id)
    return build_report(
        session_id=session.id,
        status=session.status,
        turns=repo.get_turns(db, session_id),
        meters=repo.get_meters(db, session_id),
        concern_statuses=repo.get_concern_statuses(db, session_id),
        content=content,
        client=client,
    )
