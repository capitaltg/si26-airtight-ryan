"""Golden-set regression harness (task 8).

Runs every hand-graded case in ``cases.yaml`` 3x against REAL Bedrock extraction
followed by the pure scoring engine, and asserts two things:

* **stability** — the three runs agree with each other. Extraction is
  ``temperature=0`` + forced-schema, so it should be deterministic; a swing here
  means the model is not stable on that input and the fix is a worked exemplar in
  the persona file (per docs/ideation/2-scoring-and-drift.md), not a code change.
* **validity** — the stable score matches the hand grade in ``cases.yaml``.

This is the only test that hits the network. It is marked ``golden`` and skips
when AWS credentials are absent, so the offline unit suite stays green. Run it
explicitly with::

    pytest tests/golden -m golden -v

The scored number is produced by ``score_turn`` (pure code); the model only ever
produces the ``Extraction`` it scores. The harness therefore also documents, in
one place, the full extraction -> scoring path the product depends on.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.bedrock.client import BedrockClient
from app.content.loader import Content, load_content
from app.db.models import ClaimLedger
from app.pipeline.extraction import run_extraction
from app.pipeline.scoring import score_turn

_CASES_PATH = Path(__file__).parent / "cases.yaml"
_RUNS_PER_CASE = 3


def _bedrock_available() -> bool:
    """True when the standard AWS credential chain resolves a credential.

    Extraction reads creds from the environment/IAM role (never from code), so
    the presence of a resolvable credential is what gates the live golden run.
    """
    try:
        import botocore.session  # type: ignore[import-untyped]
    except ImportError:
        return False
    return botocore.session.get_session().get_credentials() is not None


# Whole module is a live-Bedrock suite: mark it golden and skip without creds so
# `pytest` (unit CI) stays offline-green while `pytest -m golden` runs it.
pytestmark = [
    pytest.mark.golden,
    pytest.mark.skipif(
        not _bedrock_available(),
        reason="no AWS credentials; golden set needs real Bedrock access",
    ),
]


@dataclass(frozen=True)
class _Grade:
    """The three engine outputs the harness compares on."""

    support_delta: int
    capped: bool
    matched_rows: tuple[str, ...]


def _load_cases() -> list[dict[str, Any]]:
    return list(yaml.safe_load(_CASES_PATH.read_text(encoding="utf-8")))


def _prior_claims(case: dict[str, Any]) -> list[ClaimLedger]:
    """Build (unpersisted) claim-ledger rows for a case's Tier-0 context."""
    return [
        ClaimLedger(
            session_id=None,
            turn_index=row["turn_index"],
            text=row["text"],
            type=row["type"],
            backing=row.get("backing"),
            span=row["span"],
        )
        for row in case.get("prior_claims", [])
    ]


def _grade_once(case: dict[str, Any], content: Content, client: BedrockClient) -> _Grade:
    """One full extraction -> scoring pass for a case."""
    persona = content.personas[case["persona_id"]]
    concern = content.concerns[case["concern_id"]]
    result = run_extraction(
        answer=case["answer"],
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=_prior_claims(case),
        client=client,
    )
    score = score_turn(result.extraction, content.rubric)
    return _Grade(
        support_delta=score.support_delta,
        capped=score.capped,
        matched_rows=tuple(score.matched_rows),
    )


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_golden_case_is_stable_and_matches_hand_grade(case: dict[str, Any]) -> None:
    content = load_content()
    client = BedrockClient()

    grades = [_grade_once(case, content, client) for _ in range(_RUNS_PER_CASE)]

    # Stability: all three runs must agree. A swing is an extraction-drift signal.
    first = grades[0]
    assert all(g == first for g in grades), (
        f"{case['id']}: extraction unstable across {_RUNS_PER_CASE} runs: {grades}"
    )

    # Validity: the stable score must match the hand grade.
    expected = case["expected"]
    got = _Grade(
        support_delta=expected["support_delta"],
        capped=expected["capped"],
        matched_rows=tuple(expected["matched_rows"]),
    )
    assert first == got, f"{case['id']}: scored {first}, hand grade {got}"
