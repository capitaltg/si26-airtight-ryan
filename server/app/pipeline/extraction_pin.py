"""Pin one extraction per turn-input, so the score stops riding on model variance.

``score_turn`` is pure, so the same findings always produce the same number. The
findings are not: ``temperature=0`` is not reproducible on Bedrock (see
``app.bedrock.cache``). The response cache already replays byte-identical
requests, but it keys on the entire rendered prompt — RFP, proposal, persona
block, instruction strings — so any edit anywhere unpins everything. That is a
cache, not a guarantee.

This keys on the turn's *inputs* instead: the normalized answer, who asked, which
concern, the prior ledger, and a fingerprint of the authored content. Rewording a
hardcoded instruction no longer unpins; editing a persona or concern does.

What is stored is the model's raw validated tool input, not a score and not a
post-processed ``Extraction``. Anchoring, grounding, and scoring all re-run on
every replay, so a later fix to those rules reaches already-pinned inputs with no
model call — and the report's number always derives from the extraction printed
beside it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.bedrock.cache import normalize_answer
from app.db.models import ClaimLedger, ExtractionPinRow
from app.schemas.extraction import Extraction

logger = logging.getLogger(__name__)


def extraction_key(
    *,
    answer: str,
    persona_id: str,
    concern_id: str,
    prior_claims: Sequence[ClaimLedger],
    extraction_fingerprint: str,
) -> str:
    """Stable sha256 over everything that legitimately changes an extraction.

    The ledger is included in order because a Tier-0 contradiction exists only
    relative to what was said earlier — the same answer after a different history
    is a different input. ``Extraction.model_json_schema()`` is included so a
    schema change can never replay a payload that no longer validates.
    """
    payload = {
        "answer": normalize_answer(answer),
        "persona_id": persona_id,
        "concern_id": concern_id,
        "ledger": [
            {
                "turn_index": row.turn_index,
                "text": row.text,
                "type": row.type,
                "backing": row.backing,
                "span": row.span,
            }
            for row in prior_claims
        ],
        "content": extraction_fingerprint,
        "schema": Extraction.model_json_schema(),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ExtractionPin(Protocol):
    """Look up a pinned tool input, or store one. ``put`` is first-write-wins, so
    the first extraction for an input is the one that stands."""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def put(self, key: str, *, tool_input: dict[str, Any], model_id: str) -> None: ...


class NullExtractionPin:
    """Never pins anything. The default, so the golden suite stays fully live."""

    def get(self, key: str) -> dict[str, Any] | None:
        return None

    def put(self, key: str, *, tool_input: dict[str, Any], model_id: str) -> None:
        return None


class InMemoryExtractionPin:
    """Dict-backed pin for unit tests."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        row = self._rows.get(key)
        return dict(row) if row is not None else None

    def put(self, key: str, *, tool_input: dict[str, Any], model_id: str) -> None:
        self._rows.setdefault(key, dict(tool_input))


class DbExtractionPin:
    """An :class:`ExtractionPin` backed by the ``extraction_pin`` table.

    Holds the session factory, not a session: each call opens and closes its own
    short-lived session in the calling thread, which is what makes it safe from
    the SSE worker thread and keeps the pin write independent of whether the
    surrounding turn commits. Same shape as ``DbResponseCache``.

    Every failure degrades to "no pin". A read error is a miss and a write error
    is swallowed, so a database hiccup costs repeatability and never correctness:
    a scored turn must not fail because the pin store is unhappy.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            with self._session_factory() as db:
                row = db.get(ExtractionPinRow, key)
                return dict(row.tool_input) if row is not None else None
        except SQLAlchemyError:
            logger.warning("extraction pin read failed for %s; treating as a miss", key)
            return None

    def put(self, key: str, *, tool_input: dict[str, Any], model_id: str) -> None:
        try:
            with self._session_factory() as db:
                if db.get(ExtractionPinRow, key) is not None:
                    return
                db.add(
                    ExtractionPinRow(
                        input_hash=key, tool_input=tool_input, model_id=model_id
                    )
                )
                try:
                    db.commit()
                except IntegrityError:
                    # A concurrent writer pinned this key first; theirs stands.
                    db.rollback()
        except SQLAlchemyError:
            logger.warning("extraction pin write failed for %s; continuing uncached", key)
