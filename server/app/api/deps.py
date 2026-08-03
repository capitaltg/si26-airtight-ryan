"""Shared FastAPI dependencies for the API layer.

The DB session, the Bedrock client, and the voice adapters are all injected
so tests can override them (SQLite + scripted fakes) without touching the
network, AWS, or a subprocess. Content is read off ``app.state`` where the
lifespan handler stashed it at startup.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import FastAPI, Request
from sqlalchemy.orm import Session, sessionmaker

from app.bedrock.cache import DbResponseCache
from app.bedrock.client import BedrockClient
from app.config import settings
from app.content.loader import Content, load_content
from app.db.session import SessionLocal, get_db  # re-exported for routers to depend on
from app.pipeline.extraction_pin import DbExtractionPin, ExtractionPin
from app.voice.polly import synthesize_speech
from app.voice.transcribe import TranscriptionResult, measure_duration, transcribe_audio

__all__ = [
    "get_db",
    "get_content",
    "reload_content",
    "get_bedrock_client",
    "get_extraction_pin",
    "get_session_factory",
    "get_transcriber",
    "get_duration_measurer",
    "get_synthesizer",
]


def get_content(request: Request) -> Content:
    return request.app.state.content  # type: ignore[no-any-return]


def reload_content(app: FastAPI) -> Content:
    """Re-read authored content and replace the bundle on ``app.state``.

    Content is swapped as one reference: requests already in flight keep the
    bundle they read, while later requests receive this newly validated one.
    ``settings.content_dir`` is evaluated here because ``load_content`` binds
    its default argument during import.
    """
    content = load_content(settings.content_dir)
    app.state.content = content
    return content


def get_bedrock_client() -> BedrockClient:
    # Constructed per request; the AWS credential chain is read lazily. Tests
    # override this with a scripted fake. The response cache pins the first
    # output per exact request and replays it, so a rehearsal repeats identically
    # despite temperature=0 not being reproducible on Bedrock; it opens its own
    # short session per lookup/store off the same factory.
    return BedrockClient(cache=DbResponseCache(SessionLocal))


def get_extraction_pin() -> ExtractionPin:
    # Like the response cache, this opens a short-lived session per lookup and
    # store, so the streaming endpoint can use it from its worker thread.
    return DbExtractionPin(SessionLocal)


def get_session_factory() -> sessionmaker[Session]:
    """The DB session factory for callers that manage their own session outside
    the request-scoped ``get_db`` generator — e.g. the SSE streaming endpoint,
    whose blocking pipeline runs in a worker thread with its own session. Tests
    override this to point at the in-memory SQLite factory, same as ``get_db``.
    """
    return SessionLocal


class Transcriber(Protocol):
    def __call__(self, audio: bytes, content_type: str) -> TranscriptionResult: ...


class DurationMeasurer(Protocol):
    def __call__(self, audio: bytes, content_type: str) -> float: ...


class Synthesizer(Protocol):
    def __call__(self, text: str, voice_id: str) -> bytes: ...


def get_transcriber() -> Transcriber:
    # ffmpeg + AWS Transcribe live behind this indirection so tests can swap
    # in a scripted fake via `app.dependency_overrides`, same as
    # `get_bedrock_client`.
    return transcribe_audio


def get_duration_measurer() -> DurationMeasurer:
    # ffmpeg lives behind this indirection so tests can swap in a fake without
    # shelling out to a subprocess.
    return measure_duration


def get_synthesizer() -> Synthesizer:
    # AWS Polly lives behind this indirection for the same reason.
    return synthesize_speech
