"""Extraction-pin key tests: what changes the key, and what must not."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.content.loader import load_content
from app.db.models import Base, ClaimLedger, ExtractionPinRow
from app.pipeline.extraction_pin import (
    DbExtractionPin,
    InMemoryExtractionPin,
    NullExtractionPin,
    extraction_key,
)

ANSWER = "We staff three named leads at contract start."


def _key(**overrides: object) -> str:
    content = load_content()
    kwargs: dict[str, object] = {
        "answer": ANSWER,
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "prior_claims": [],
        "prior_answers": {},
        "extraction_fingerprint": content.extraction_fingerprint,
    }
    kwargs.update(overrides)
    return extraction_key(**kwargs)  # type: ignore[arg-type]


def test_same_input_gives_the_same_key() -> None:
    assert _key() == _key()
    assert len(_key()) == 64


def test_whitespace_and_case_variants_share_a_key() -> None:
    assert _key(answer="  WE  STAFF   three named\nleads at contract start. ") == _key()


def test_different_answer_changes_the_key() -> None:
    assert _key(answer="We have not decided yet.") != _key()


def test_different_persona_or_concern_changes_the_key() -> None:
    assert _key(persona_id="contracting_officer") != _key()
    assert _key(concern_id="past_performance") != _key()


def test_different_prior_claims_change_the_key() -> None:
    ledger = [
        ClaimLedger(
            session_id=None,
            turn_index=0,
            text="We staff two leads.",
            type="commitment",
            backing="bare",
            span="two leads",
        )
    ]
    assert _key(prior_claims=ledger) != _key()


def test_content_fingerprint_change_changes_the_key() -> None:
    assert _key(extraction_fingerprint="0" * 64) != _key()


def test_different_prior_answers_change_the_key() -> None:
    """Same answer and ledger, different stored history: grounding reads
    ``prior_answers`` to decide a Tier-0 flag, so it must be part of the key."""
    assert _key(prior_answers={0: "We have not identified the leads yet."}) != _key()


def test_in_memory_pin_round_trips() -> None:
    pin = InMemoryExtractionPin()
    assert pin.get("k") is None
    pin.put("k", tool_input={"claims": []}, model_id="m")
    assert pin.get("k") == {"claims": []}


def test_in_memory_pin_is_first_write_wins() -> None:
    pin = InMemoryExtractionPin()
    pin.put("k", tool_input={"claims": ["first"]}, model_id="m")
    pin.put("k", tool_input={"claims": ["second"]}, model_id="m")
    assert pin.get("k") == {"claims": ["first"]}


def test_null_pin_never_stores() -> None:
    pin = NullExtractionPin()
    pin.put("k", tool_input={"claims": []}, model_id="m")
    assert pin.get("k") is None


def _factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_db_pin_round_trips_across_instances() -> None:
    factory = _factory()
    DbExtractionPin(factory).put("k", tool_input={"claims": []}, model_id="m")
    assert DbExtractionPin(factory).get("k") == {"claims": []}


def test_db_pin_is_first_write_wins() -> None:
    factory = _factory()
    pin = DbExtractionPin(factory)
    pin.put("k", tool_input={"claims": ["first"]}, model_id="m")
    pin.put("k", tool_input={"claims": ["second"]}, model_id="m")
    assert pin.get("k") == {"claims": ["first"]}
    with factory() as db:
        assert db.query(ExtractionPinRow).count() == 1


def test_db_pin_read_failure_is_a_miss_not_an_error() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)  # no tables created
    pin = DbExtractionPin(sessionmaker(bind=engine))
    assert pin.get("k") is None


def test_db_pin_write_failure_is_swallowed() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)  # no tables created
    pin = DbExtractionPin(sessionmaker(bind=engine))
    pin.put("k", tool_input={"claims": []}, model_id="m")  # must not raise
