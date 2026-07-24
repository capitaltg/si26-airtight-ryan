"""Response-replay cache for the Bedrock choke point.

``temperature=0`` alone is not reproducible on Bedrock (greedy decoding still
varies with backend batching, floating-point order, and endpoint routing, and
the Anthropic Messages API exposes no ``seed``). To make a rehearsal repeatable
we store the first successful model output per exact request and replay it when
the same request recurs — the deterministic option that holds regardless of
backend behavior.

The cache is a thin protocol so the client stays testable with an in-memory
fake, plus a DB-backed implementation used in the running app. The key is a
hash of the full request; identical bytes across two runs collide on purpose,
which is exactly the reproducibility guarantee. A versioned-content change alters
the prompt bytes and therefore the key, so stale entries fall out on their own.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ModelResponseCache


def request_key(
    *,
    method: str,
    model: str,
    max_tokens: int,
    content: str | list[dict[str, Any]],
    tool_name: str | None = None,
    schema: dict[str, Any] | None = None,
) -> str:
    """Stable sha256 over everything that can change the model output.

    ``content`` is the prompt string or the exact block list; ``schema`` and
    ``tool_name`` are included for the forced-tool ``extract`` path because the
    tool definition is part of the request the model sees. ``sort_keys`` makes
    the digest independent of dict ordering, and ``default=str`` keeps it from
    raising on any stray non-JSON value rather than silently dropping it.
    """
    payload = {
        "method": method,
        "model": model,
        "max_tokens": max_tokens,
        "content": content,
        "tool_name": tool_name,
        "schema": schema,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResponseCache(Protocol):
    """The slice of behaviour the client needs: look up a stored response, or
    store one. ``put`` is first-write-wins so the first response for a request is
    the one that is pinned forever."""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, method: str, value: dict[str, Any]) -> None: ...


class DbResponseCache:
    """A :class:`ResponseCache` backed by the ``model_response_cache`` table.

    It manages its own short-lived session per call rather than borrowing the
    request's transaction: the cache read/write must not be tied to whether the
    surrounding turn commits, and the streaming path runs the pipeline in a
    worker thread with a different session anyway. Writes are first-write-wins —
    a concurrent second writer racing on the same key loses harmlessly to an
    ``IntegrityError`` on the primary key, and the already-stored response stands.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, key: str) -> dict[str, Any] | None:
        with self._session_factory() as db:
            row = db.get(ModelResponseCache, key)
            return dict(row.response_json) if row is not None else None

    def put(self, key: str, method: str, value: dict[str, Any]) -> None:
        with self._session_factory() as db:
            if db.get(ModelResponseCache, key) is not None:
                return
            db.add(
                ModelResponseCache(
                    request_hash=key, method=method, response_json=value
                )
            )
            try:
                db.commit()
            except IntegrityError:
                # Another writer stored this key first; theirs wins, drop ours.
                db.rollback()
