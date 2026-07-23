"""Session API — create a rehearsal, submit answers, end, and read the report.

The router is a thin HTTP shell over the code-driven orchestrator: it never
scores or selects concerns itself. DTOs here are the contract the frontend
mirrors in ``types.ts`` (task 11).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_bedrock_client, get_content, get_db, get_session_factory
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


def _answer_payload(
    db: Session, session_id: uuid.UUID, result: orchestrator.TurnResult
) -> AnswerResponse:
    """The AnswerResponse for one scored turn. Shared by the plain-JSON
    ``/answer`` endpoint and the SSE ``/answer/stream`` result frame so both
    carry byte-identical fields."""
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
        meters=_meters(db, session_id),
        next_prompt=_prompt_dto(result.next),
        done=result.done,
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
    return _answer_payload(db, session.id, result)


# Sentinel put on the queue by the worker thread when the stream is exhausted.
_DONE = object()


@router.post("/{session_id}/answer/stream")
async def submit_answer_stream(
    session_id: uuid.UUID,
    body: AnswerRequest,
    content: Content = Depends(get_content),
    client: BedrockClient = Depends(get_bedrock_client),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> StreamingResponse:
    """Streaming twin of ``/answer``: emits SSE ``data:`` frames tagged by key —
    ``{"stage": ...}`` at each pipeline boundary, then one ``{"result": {...}}``
    (the same payload ``/answer`` returns) or ``{"error": ...}``.

    The pipeline is blocking and synchronous, so it runs in one worker thread
    with its own DB session (clean thread affinity — no cross-thread SQLAlchemy
    use), bridged to the async response via an ``asyncio.Queue``.
    """
    queue: asyncio.Queue[object] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(ev: object) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def worker() -> None:
        db = session_factory()
        try:
            session = repo.get_session(db, session_id)
            if session is None:
                emit({"error": "session not found"})
                return
            for ev in orchestrator.submit_answer_events(
                db, content, client, session, body.answer
            ):
                if "result" in ev:
                    result = cast(orchestrator.TurnResult, ev["result"])
                    payload = _answer_payload(db, session_id, result).model_dump(mode="json")
                    emit({"result": payload})
                else:
                    emit(ev)
            db.commit()
        except SessionComplete as exc:
            db.rollback()
            emit({"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — surface any pipeline failure as an SSE error frame
            db.rollback()
            emit({"error": str(exc)})
        finally:
            db.close()
            emit(_DONE)

    async def event_stream() -> AsyncIterator[str]:
        # Hold the reference: a bare create_task can be garbage-collected
        # mid-flight. The worker runs to completion and closes its own DB session
        # in `finally`, so a client disconnect leaks nothing (the thread can't be
        # preempted in any case); it just self-terminates on the next iteration.
        task = asyncio.ensure_future(asyncio.to_thread(worker))
        try:
            while True:
                ev = await queue.get()
                if ev is _DONE:
                    break
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
