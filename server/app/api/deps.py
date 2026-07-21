"""Shared FastAPI dependencies for the API layer.

Both the DB session and the Bedrock client are injected so tests can override
them (SQLite + a scripted fake) without touching the network. Content is read
off ``app.state`` where the lifespan handler stashed it at startup.
"""

from __future__ import annotations

from fastapi import Request

from app.bedrock.client import BedrockClient
from app.content.loader import Content
from app.db.session import get_db  # re-exported for routers to depend on

__all__ = ["get_db", "get_content", "get_bedrock_client"]


def get_content(request: Request) -> Content:
    return request.app.state.content  # type: ignore[no-any-return]


def get_bedrock_client() -> BedrockClient:
    # Constructed per request; the AWS credential chain is read lazily. Tests
    # override this with a scripted fake.
    return BedrockClient()
