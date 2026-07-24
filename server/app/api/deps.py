"""Shared FastAPI dependencies for the API layer.

Both the DB session and the Bedrock client are injected so tests can override
them (SQLite + a scripted fake) without touching the network. Content is read
off ``app.state`` where the lifespan handler stashed it at startup.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.bedrock.cache import DbResponseCache
from app.bedrock.client import BedrockClient
from app.content.loader import Content
from app.db.session import SessionLocal, get_db  # re-exported for routers to depend on

__all__ = ["get_db", "get_content", "get_bedrock_client", "get_session_factory"]


def get_content(request: Request) -> Content:
    return request.app.state.content  # type: ignore[no-any-return]


def get_bedrock_client() -> BedrockClient:
    # Constructed per request; the AWS credential chain is read lazily. Tests
    # override this with a scripted fake. The response cache pins the first
    # output per exact request and replays it, so a rehearsal repeats identically
    # despite temperature=0 not being reproducible on Bedrock; it opens its own
    # short session per lookup/store off the same factory.
    return BedrockClient(cache=DbResponseCache(SessionLocal))


def get_session_factory() -> sessionmaker[Session]:
    """The DB session factory for callers that manage their own session outside
    the request-scoped ``get_db`` generator — e.g. the SSE streaming endpoint,
    whose blocking pipeline runs in a worker thread with its own session. Tests
    override this to point at the in-memory SQLite factory, same as ``get_db``.
    """
    return SessionLocal
