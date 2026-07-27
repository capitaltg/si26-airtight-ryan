"""Tier-0 consistency flags must point at something the presenter actually said.

The model was raising `consistency_flags` for conflicts with the RFP and the
written proposal (which is Tier-1, and already scores as `false_fact`), and
raising them on the first turn of a session where the claim ledger is empty and
there is nothing to contradict. Both cost the presenter a point the rubric never
authorized. See docs/issues/tier-0-contradiction-fires-on-document-conflicts.md.

The prompt tells the model the rule; this guard enforces it in code, so a
mislabeled flag cannot reach the scorer even when the model ignores the prompt.
"""

from typing import Any

from app.db.models import ClaimLedger
from app.pipeline.extraction import (
    build_extraction_dynamic_suffix,
    drop_unanchored_flags,
    run_extraction,
)
from app.schemas.extraction import ConsistencyFlag, Extraction

from .test_extraction import FakeBedrockClient, _fixture, _prior_claims


def _flagged(*turns: int) -> Extraction:
    return Extraction(
        consistency_flags=[
            ConsistencyFlag(conflicts_with_turn=t, detail=f"conflicts with turn {t}")
            for t in turns
        ]
    )


def _run(extraction: Extraction, prior: list[ClaimLedger]) -> Any:
    content, persona, concern = _fixture()
    return run_extraction(
        answer="We staff three named leads on day one.",
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=prior,
        client=FakeBedrockClient(extraction),  # type: ignore[arg-type]
    )


def test_flag_on_an_empty_ledger_is_dropped() -> None:
    """First scored turn of a session: nothing exists to contradict."""
    kept = drop_unanchored_flags(_flagged(0), [])

    assert kept.consistency_flags == []


def test_flag_pointing_at_a_real_prior_turn_survives() -> None:
    prior = _prior_claims()  # turns 0 and 1

    kept = drop_unanchored_flags(_flagged(1), prior)

    assert [f.conflicts_with_turn for f in kept.consistency_flags] == [1]


def test_flag_pointing_past_the_ledger_is_dropped() -> None:
    """`conflicts_with_turn: 5` with two prior turns names a turn that never happened."""
    kept = drop_unanchored_flags(_flagged(5), _prior_claims())

    assert kept.consistency_flags == []


def test_real_and_bogus_flags_are_separated() -> None:
    kept = drop_unanchored_flags(_flagged(0, 9), _prior_claims())

    assert [f.conflicts_with_turn for f in kept.consistency_flags] == [0]


def test_dropping_flags_leaves_every_other_field_alone() -> None:
    """The guard touches consistency_flags only — fact checks in particular, since
    a document conflict belongs there and must still score as `false_fact`."""
    extraction = Extraction(
        consistency_flags=[ConsistencyFlag(conflicts_with_turn=0, detail="bogus")],
        fact_checks=[
            {"claim": "42 million records", "tier": 1, "verdict": "refuted", "source": "PWS 3.1"}  # type: ignore[list-item]
        ],
    )

    kept = drop_unanchored_flags(extraction, [])

    assert kept.consistency_flags == []
    assert len(kept.fact_checks) == 1
    assert kept.fact_checks[0].claim == "42 million records"


def test_run_extraction_applies_the_guard() -> None:
    """End to end: a model flag on an empty ledger never reaches the scorer."""
    result = _run(_flagged(0), [])

    assert result.extraction.consistency_flags == []


def test_run_extraction_keeps_a_genuine_tier0_flag() -> None:
    result = _run(_flagged(0), _prior_claims())

    assert len(result.extraction.consistency_flags) == 1


def test_suffix_sends_document_conflicts_to_the_fact_checks_field() -> None:
    """The prompt has to name the right home for a Tier-1 conflict, or the model
    keeps filing it under consistency_flags."""
    content, _persona, concern = _fixture()

    suffix = build_extraction_dynamic_suffix(
        answer="An answer.", concern=concern, prior_claims=_prior_claims()
    )

    assert "fact_checks" in suffix
    assert "consistency_flags" in suffix
    assert content.rfp_text.strip()[:40] not in suffix  # still no cached context


def test_suffix_states_the_empty_ledger_rule() -> None:
    suffix = build_extraction_dynamic_suffix(
        answer="An answer.", concern=_fixture()[2], prior_claims=[]
    )

    assert "no prior claims" in suffix
    assert "consistency_flags" in suffix
