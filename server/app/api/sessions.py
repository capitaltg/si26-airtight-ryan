"""Session API — create a rehearsal, submit answers, end, and read the report.

The router is a thin HTTP shell over the code-driven orchestrator: it never
scores or selects concerns itself. DTOs here are the contract the frontend
mirrors in ``types.ts`` (task 11).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    Synthesizer,
    Transcriber,
    get_bedrock_client,
    get_content,
    get_db,
    get_session_factory,
    get_synthesizer,
    get_transcriber,
)
from app.bedrock.client import BedrockClient
from app.config import settings
from app.content.loader import Content
from app.db import repo
from app.db.models import Clarification, RehearsalSession, Turn
from app.pipeline import orchestrator
from app.pipeline.orchestrator import AnswerAudio, ClarificationCapReached, SessionComplete
from app.report.builder import build_report
from app.schemas.reaction import PersonaReaction
from app.schemas.report import Report
from app.schemas.scoring import ScoreOutput
from app.session_archive import archive_session
from app.voice import SynthesisError, TranscriptionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])

# The browser-recorded container types this app ever expects (see
# `frontend/src/audio.ts`'s `MIME_CANDIDATES`, plus the codec-parameter
# variants browsers actually send, e.g. "audio/webm;codecs=opus"). Anything
# else is client-controlled and untrusted: `content_type` is persisted and
# later echoed back verbatim as the `media_type` on `GET .../turns/{i}/audio`,
# so an unvalidated value is a stored-XSS vector (e.g. "text/html") and can
# also exceed the `answer_audio_content_type` column's `String(64)` limit.
_ALLOWED_AUDIO_CONTENT_TYPE_PREFIXES = ("audio/webm", "audio/mp4", "audio/ogg")
_SAFE_DEFAULT_AUDIO_CONTENT_TYPE = "application/octet-stream"
# Matches `answer_audio_content_type`'s `String(64)` column (app/db/models.py) —
# an allowlisted-prefix value that's still too long to store falls back to the
# safe default rather than blowing up at commit time on a DB that enforces the
# column length (e.g. Postgres), after the (paid) transcription call already ran.
_MAX_AUDIO_CONTENT_TYPE_LENGTH = 64


def _safe_audio_content_type(content_type: str) -> str:
    """Pass through only an allowlisted container type that also fits the DB
    column; anything else falls back to a safe, generic type. This is purely a
    replay-header safeguard — ffmpeg sniffs the real container from the bytes
    regardless of what's claimed here (see `app/voice/audio.py`), so the
    upload is never rejected for a mismatched-but-unrecognized content type."""
    if (
        content_type.lower().startswith(_ALLOWED_AUDIO_CONTENT_TYPE_PREFIXES)
        and len(content_type) <= _MAX_AUDIO_CONTENT_TYPE_LENGTH
    ):
        return content_type
    return _SAFE_DEFAULT_AUDIO_CONTENT_TYPE


class MeterDTO(BaseModel):
    persona_id: str
    support: int
    capped: bool


class PromptDTO(BaseModel):
    persona_id: str
    display_name: str
    concern_id: str
    prompt: str
    is_follow_up: bool
    # The persona's self-introduction, non-null only on the first prompt they
    # ask in this session. Its own field rather than part of `prompt`, so the
    # stored turn and the report keep showing only the question.
    intro: str | None = None


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


class VoiceAnswerResponse(AnswerResponse):
    transcript: str
    reply_audio: str | None  # base64 mp3, null if synthesis failed
    next_prompt_audio: str | None  # base64 mp3, null at end of session or on failure


class ClarifyRequest(BaseModel):
    question: str


class ClarifyResponse(BaseModel):
    reply: str
    persona_id: str
    concern_id: str
    remaining: int  # clarifications left on this concern
    prompt: PromptDTO  # unchanged active prompt


class PromptAudioDTO(BaseModel):
    audio: str | None  # base64 mp3, null if synthesis failed


class HistorySummaryDTO(BaseModel):
    """One card in the past-rehearsals list. Everything here is derived from
    rows that already existed; nothing is stored for the list itself."""

    id: uuid.UUID
    created_at: datetime
    archived_at: datetime
    status: str  # "complete" | "ended"
    turn_count: int
    meters: list[MeterDTO]
    concerns_satisfied: int
    concerns_total: int


class ArchivedTurnDTO(BaseModel):
    """One exchange read back from the stored rows. Field names mirror the
    frontend's `TranscriptTurn`, so `ChatTurn` renders an archived turn with no
    change."""

    persona_id: str
    display_name: str
    concern_id: str
    is_follow_up: bool
    prompt: str
    intro: str | None
    answer: str
    reply: str
    rationale: str
    support_delta: int
    matched_rows: list[str]
    capped: bool
    scored: bool  # False for a clarification exchange
    transcript: str | None  # voice turns only


class TranscriptDTO(BaseModel):
    turns: list[ArchivedTurnDTO]


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
        display_name=asg.persona.display_name,
        concern_id=asg.concern.concern_id,
        prompt=asg.prompt,
        is_follow_up=asg.is_follow_up,
        intro=asg.intro,
    )


def _spoken_prompt_text(asg: orchestrator.Assignment) -> str:
    """The prompt as it should be *heard*. On a persona's first prompt of a
    session the intro leads and the question follows, as one line in one voice."""
    if not asg.intro:
        return asg.prompt
    return f"{asg.intro} {asg.prompt}"


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


def _display_name(content: Content, persona_id: str) -> str:
    """The persona's authored name, or their id if the persona was removed from
    content after this session was archived."""
    persona = content.personas.get(persona_id)
    return persona.display_name if persona is not None else persona_id


def _asked_prompt(content: Content, concern_id: str, stored: str | None) -> str:
    """The stored prompt, falling back to the content core ask for rows written
    before migration 0006 (and to empty when that concern is also gone)."""
    if stored:
        return stored
    concern = content.concerns.get(concern_id)
    return concern.core_ask if concern is not None else ""


def _archived_turns(
    db: Session, content: Content, session_id: uuid.UUID
) -> list[ArchivedTurnDTO]:
    """Scored turns and clarifications merged into one `created_at`-ordered list.

    The sort key carries two extra components because `created_at` comes from
    `CURRENT_TIMESTAMP`, which has one-second resolution on SQLite: within one
    second, clarifications come before turns (a clarification is always asked
    against the still-active prompt, before the answer that resolves it, so a
    same-second tie is a clarification immediately followed by the turn it led
    to) and each kind orders by its own monotonic key, so the list is
    deterministic rather than insertion-order-dependent.
    """
    rows: list[tuple[datetime, int, int, Turn | Clarification]] = [
        (turn.created_at, 1, turn.turn_index, turn) for turn in repo.get_turns(db, session_id)
    ] + [
        (row.created_at, 0, row.id, row) for row in repo.get_clarifications(db, session_id)
    ]
    rows.sort(key=lambda row: (row[0], row[1], row[2]))

    # A concern seen before means this is a repeat press on it. Only scored turns
    # count: a clarification never advances the agenda or earns a follow-up.
    scored_concerns: set[str] = set()
    out: list[ArchivedTurnDTO] = []
    for _, _, _, row in rows:
        if isinstance(row, Turn):
            score = ScoreOutput.model_validate(row.score_json)
            reaction = (
                PersonaReaction.model_validate(row.reaction_json)
                if row.reaction_json is not None
                else None
            )
            is_follow_up = row.concern_id in scored_concerns
            scored_concerns.add(row.concern_id)
            out.append(
                ArchivedTurnDTO(
                    persona_id=row.persona_id,
                    display_name=_display_name(content, row.persona_id),
                    concern_id=row.concern_id,
                    is_follow_up=is_follow_up,
                    prompt=_asked_prompt(content, row.concern_id, row.prompt),
                    intro=row.prompt_intro,
                    answer=row.user_answer,
                    reply=reaction.in_character_reply if reaction is not None else "",
                    rationale=reaction.rationale if reaction is not None else "",
                    support_delta=score.support_delta,
                    matched_rows=score.matched_rows,
                    # The per-turn red-line flag, which is the auditable fact
                    # about this answer. The persona's sticky meter cap is a
                    # session-level fact and shows on the meters.
                    capped=score.capped,
                    scored=True,
                    transcript=row.transcript,
                )
            )
        else:
            out.append(
                ArchivedTurnDTO(
                    persona_id=row.persona_id,
                    display_name=_display_name(content, row.persona_id),
                    concern_id=row.concern_id,
                    is_follow_up=row.concern_id in scored_concerns,
                    prompt=_asked_prompt(content, row.concern_id, row.prompt),
                    intro=None,
                    answer=row.question,
                    reply=row.reply,
                    rationale="",
                    support_delta=0,
                    matched_rows=[],
                    capped=False,
                    scored=False,
                    transcript=None,
                )
            )
    return out


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


def _speak(synthesizer: Synthesizer, text: str, voice_id: str) -> str | None:
    """Synthesize speech for one line, base64-encoded for JSON transport. A
    synthesis failure never costs the presenter a scored turn — it just means
    no audio rides along with an otherwise-normal response."""
    try:
        audio = synthesizer(text, voice_id)
    except SynthesisError:
        logger.exception("speech synthesis failed")
        return None
    return base64.b64encode(audio).decode()


@router.post("", response_model=SessionStateDTO, status_code=201)
def create_session(
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
) -> SessionStateDTO:
    # Retention runs here, before the new row exists, so the session being
    # created is never a deletion candidate.
    repo.prune_history(
        db,
        keep=settings.history_keep,
        abandoned_ttl_hours=settings.abandoned_session_ttl_hours,
    )
    session = orchestrator.start_session(db, content)
    return _state(db, content, session)


# Declared before `GET /{session_id}`: FastAPI matches in declaration order, so
# the other way around "history" is parsed as the `session_id` UUID path
# parameter and the request 422s.
@router.get("/history", response_model=list[HistorySummaryDTO])
def get_history(db: Session = Depends(get_db)) -> list[HistorySummaryDTO]:
    """The most recent finished rehearsals, newest first."""
    rows: list[HistorySummaryDTO] = []
    for session in repo.list_archived_sessions(db, limit=settings.history_keep):
        assert session.archived_at is not None  # guaranteed by the query's filter
        statuses = repo.get_concern_statuses(db, session.id)
        rows.append(
            HistorySummaryDTO(
                id=session.id,
                created_at=session.created_at,
                archived_at=session.archived_at,
                status=session.status,
                turn_count=len(repo.get_turns(db, session.id)),
                meters=_meters(db, session.id),
                concerns_satisfied=sum(1 for s in statuses.values() if s == "satisfied"),
                concerns_total=len(statuses),
            )
        )
    return rows


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
    if result.done:
        archive_session(db, content, client, session)
    return _answer_payload(db, session.id, result)


@router.post("/{session_id}/answer_audio", response_model=VoiceAnswerResponse)
def submit_answer_audio(
    session_id: uuid.UUID,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
    client: BedrockClient = Depends(get_bedrock_client),
    transcriber: Transcriber = Depends(get_transcriber),
    synthesizer: Synthesizer = Depends(get_synthesizer),
) -> VoiceAnswerResponse:
    """Voice twin of ``/answer``: transcribe the recording, then run the exact
    same ``orchestrator.submit_answer`` call the text path uses (the fixed
    transcript standing in for the typed answer), so a presenter's spoken
    answer scores byte-identically to the same words typed.

    Ordering matters for the "no silent score" guarantee: transcription
    happens before anything touches the DB, so a failed or blank transcript
    leaves the session completely untouched (no turn row, no meter movement).
    """
    session = _require_session(db, session_id)

    data = audio.file.read()
    if not data:
        raise HTTPException(status_code=422, detail="empty audio upload")
    if len(data) > settings.max_answer_audio_bytes:
        raise HTTPException(status_code=413, detail="audio upload too large")

    content_type = _safe_audio_content_type(audio.content_type or "audio/webm")
    try:
        transcript = transcriber(data, content_type)
    except TranscriptionError:
        logger.exception("transcription failed for session %s", session_id)
        raise HTTPException(
            status_code=422, detail="Could not transcribe the recording"
        ) from None
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe the recording")

    try:
        result = orchestrator.submit_answer(
            db,
            content,
            client,
            session,
            transcript,
            audio=AnswerAudio(data=data, content_type=content_type, transcript=transcript),
        )
    except SessionComplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if result.done:
        archive_session(db, content, client, session)

    persona = content.personas[result.persona_id]
    reply_audio = _speak(synthesizer, result.reaction.in_character_reply, persona.polly_voice_id)
    next_prompt_audio = None
    if result.next is not None:
        # On a handoff the incoming persona introduces themself and asks in the
        # same breath: one Polly call, one clip, one voice, so playSequence and
        # the replay route need no change.
        next_prompt_audio = _speak(
            synthesizer,
            _spoken_prompt_text(result.next),
            result.next.persona.polly_voice_id,
        )

    return VoiceAnswerResponse(
        **_answer_payload(db, session.id, result).model_dump(),
        transcript=transcript,
        reply_audio=reply_audio,
        next_prompt_audio=next_prompt_audio,
    )


@router.get("/{session_id}/turns/{turn_index}/audio")
def get_turn_audio(
    session_id: uuid.UUID,
    turn_index: int,
    db: Session = Depends(get_db),
) -> Response:
    """Replay the recording behind one scored turn, or 404 if that turn was
    answered via the text path (no audio was ever attached)."""
    turns = repo.get_turns(db, session_id)
    turn = next((t for t in turns if t.turn_index == turn_index), None)
    if turn is None or turn.answer_audio is None:
        raise HTTPException(status_code=404, detail="no audio for this turn")
    return Response(content=turn.answer_audio, media_type=turn.answer_audio_content_type)


@router.get("/{session_id}/transcript", response_model=TranscriptDTO)
def get_transcript(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
) -> TranscriptDTO:
    """The rehearsal's exchanges, rebuilt from the stored rows rather than from a
    snapshot: turns and clarifications already are the audit trail. Works on a
    live session too, returning the turns so far."""
    session = _require_session(db, session_id)
    return TranscriptDTO(turns=_archived_turns(db, content, session.id))


@router.get("/{session_id}/prompt_audio", response_model=PromptAudioDTO)
def get_prompt_audio(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
    synthesizer: Synthesizer = Depends(get_synthesizer),
) -> PromptAudioDTO:
    """Speak the active prompt on demand, intro and question in one clip.

    Called when the presenter switches to voice mode. The toggle click is the
    user gesture the browser's autoplay policy needs, which `POST /sessions`
    never has — that is why the opening prompt can be spoken here and not at
    session start.

    Read-only by design: it resolves the active assignment through the same
    `next_concern` call `_state` uses (so the intro is present here exactly when
    it is present on the `PromptDTO` the presenter is looking at) and writes
    nothing. Re-toggling costs a Polly call and no session state.
    """
    session = _require_session(db, session_id)
    asg = orchestrator.next_concern(db, content, session)
    if asg is None:
        raise HTTPException(status_code=409, detail="session is already complete")
    return PromptAudioDTO(
        audio=_speak(synthesizer, _spoken_prompt_text(asg), asg.persona.polly_voice_id)
    )


@router.post("/{session_id}/clarify", response_model=ClarifyResponse)
def clarify(
    session_id: uuid.UUID,
    body: ClarifyRequest,
    db: Session = Depends(get_db),
    content: Content = Depends(get_content),
    client: BedrockClient = Depends(get_bedrock_client),
) -> ClarifyResponse:
    """Answer a clarifying question without scoring the turn. The active prompt is
    echoed back unchanged; no meter, ledger, agenda, or attempt count moves."""
    session = _require_session(db, session_id)
    try:
        result = orchestrator.ask_clarification(db, content, client, session, body.question)
    except SessionComplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ClarificationCapReached as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    prompt = _prompt_dto(result.prompt)
    assert prompt is not None  # ask_clarification returns the active (non-None) prompt
    return ClarifyResponse(
        reply=result.reply,
        persona_id=result.persona_id,
        concern_id=result.concern_id,
        remaining=result.remaining,
        prompt=prompt,
    )


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
                    # Before the commit below, on this worker's own session, so
                    # the result frame the client receives already reflects an
                    # archived session.
                    if result.done:
                        archive_session(db, content, client, session)
                    payload = _answer_payload(db, session_id, result).model_dump(mode="json")
                    emit({"result": payload})
                else:
                    emit(ev)
            db.commit()
        except SessionComplete as exc:
            # Domain-meaningful and already surfaced verbatim by /answer (409); safe
            # to pass through so the frontend shows the same "session complete" text.
            db.rollback()
            emit({"error": str(exc)})
        except Exception:
            # Mirror /answer's opaque 500: log the real error server-side, never
            # leak internal exception text to the client.
            db.rollback()
            logger.exception("streaming answer failed for session %s", session_id)
            emit({"error": "internal error"})
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
    client: BedrockClient = Depends(get_bedrock_client),
) -> SessionStateDTO:
    """End the rehearsal and archive it. `archive_session` owns the status write:
    it sets "complete" when the agenda happened to be exhausted and "ended"
    otherwise, so this path and the answer paths agree by construction."""
    session = _require_session(db, session_id)
    archive_session(db, content, client, session)
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
    if session.report_json is not None:
        # Archived: return the bytes snapshotted at finish. No model call, and no
        # re-render against content that may have bumped since.
        return Report.model_validate(session.report_json)
    return build_report(
        session_id=session.id,
        status=session.status,
        turns=repo.get_turns(db, session_id),
        meters=repo.get_meters(db, session_id),
        concern_statuses=repo.get_concern_statuses(db, session_id),
        content=content,
        client=client,
        clarifications=repo.get_clarifications(db, session_id),
    )
