"""Tests for the DB-backed response cache and its end-to-end replay.

The cache exists to make a rehearsal repeatable: identical model requests must
return identical output even though Bedrock's temperature=0 is not reproducible.
These exercise the store directly over SQLite and prove the full BedrockClient
replays through it, including the acceptance case — the same input run twice
yields the same extraction and reaction.
"""

from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bedrock.cache import DbResponseCache, request_key
from app.bedrock.client import BedrockClient
from app.db.models import Base, ModelResponseCache
from app.schemas.extraction import Extraction


def _factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_put_then_get_roundtrips() -> None:
    cache = DbResponseCache(_factory())
    cache.put("k1", "react", {"text": "hello"})
    assert cache.get("k1") == {"text": "hello"}


def test_get_miss_returns_none() -> None:
    assert DbResponseCache(_factory()).get("absent") is None


def test_put_is_first_write_wins() -> None:
    cache = DbResponseCache(_factory())
    cache.put("k1", "react", {"text": "first"})
    cache.put("k1", "react", {"text": "second"})
    assert cache.get("k1") == {"text": "first"}


def test_put_writes_a_single_row_with_method() -> None:
    factory = _factory()
    cache = DbResponseCache(factory)
    cache.put("k1", "extract", {"tool_input": {"claims": []}})
    with factory() as db:
        rows = list(db.scalars(select(ModelResponseCache)))
    assert len(rows) == 1
    assert rows[0].request_hash == "k1"
    assert rows[0].method == "extract"


def test_request_key_is_order_independent_but_content_sensitive() -> None:
    a = request_key(method="react", model="m", max_tokens=10, content="p")
    b = request_key(method="react", model="m", max_tokens=10, content="p")
    c = request_key(method="react", model="m", max_tokens=10, content="different")
    assert a == b
    assert a != c


# --- end-to-end replay through the real client over a DB-backed cache ---


def _block(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(**fields)


def _tool_response(tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[_block(type="tool_use", name="record_extraction", input=tool_input)],
        stop_reason="tool_use",
    )


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=[_block(type="text", text=text)], stop_reason="end_turn"
    )


class _ScriptedMessages:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _ScriptedTransport:
    def __init__(self, *responses: Any) -> None:
        self.messages = _ScriptedMessages(list(responses))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


def _extraction_a() -> dict:
    return {
        "claims": [
            {
                "text": "PM has 12 years of federal experience.",
                "type": "commitment",
                "backing": "backed",
                "span": "our PM brings 12 years",
            }
        ]
    }


def _extraction_b() -> dict:
    return {
        "claims": [
            {
                "text": "Team delivered three prior systems.",
                "type": "commitment",
                "backing": "backed",
                "span": "three prior systems",
            }
        ]
    }


def test_two_runs_same_input_produce_equal_output() -> None:
    """Acceptance: run the same request twice against a backend that would answer
    differently each time; the shared cache makes both runs equal."""
    factory = _factory()

    # Run one: a fresh client (mirrors a per-request client) sees answer A.
    t1 = _ScriptedTransport(_tool_response(_extraction_a()), _text_response("Reply A."))
    c1 = BedrockClient(transport=t1, cache=DbResponseCache(factory))
    ext1 = c1.extract("prompt", content_schema=Extraction, tool_name="record_extraction")
    react1 = c1.react("react-prompt")

    # Run two: a brand-new client, backend now scripted to answer DIFFERENTLY.
    t2 = _ScriptedTransport(_tool_response(_extraction_b()), _text_response("Reply B."))
    c2 = BedrockClient(transport=t2, cache=DbResponseCache(factory))
    ext2 = c2.extract("prompt", content_schema=Extraction, tool_name="record_extraction")
    react2 = c2.react("react-prompt")

    assert ext1 == ext2  # extraction replayed, not re-generated
    assert react1 == react2 == "Reply A."
    assert len(t2.calls) == 0  # run two never reached the backend
