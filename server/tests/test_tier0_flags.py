"""Tier-0 consistency flags must point at a stored prior answer, with both the
current and prior spans verbatim in their respective answers.

The model was raising `consistency_flags` for conflicts with the RFP and the
written proposal (which is Tier-1, and already scores as `false_fact`), and
raising them on the first turn of a session where there is no stored answer to
contradict. Both cost the presenter a point the rubric never authorized. See
docs/issues/tier-0-contradiction-fires-on-document-conflicts.md.

The prompt tells the model the rule; this guard (now `drop_ungrounded`, in
`app.pipeline.grounding`) enforces it in code, so a mislabeled or fabricated
flag cannot reach the scorer even when the model ignores the prompt.
"""

from typing import Any

from app.db.models import ClaimLedger
from app.pipeline.extraction import build_extraction_dynamic_suffix, run_extraction
from app.pipeline.grounding import drop_ungrounded
from app.schemas.extraction import ConsistencyFlag, Extraction, SourceDocument

from .test_extraction import FakeBedrockClient, _fixture, _prior_claims

ANSWER = "We staff three named leads on day one."


def _flagged(*turns: int) -> Extraction:
    return Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=t,
                current_answer_span="three named leads on day one",
                prior_answer_span=f"conflicts with turn {t}",
                acknowledged_revision=False,
            )
            for t in turns
        ]
    )


def _prior_answers(*turns: int) -> dict[int, str]:
    """Stored prior answers whose text quotes ``_flagged``'s prior_answer_span
    for each named turn, so a flag naming one of these turns is grounded."""
    return {t: f"Turn {t}'s answer, which conflicts with turn {t}." for t in turns}


def _drop(extraction: Extraction, prior_answers: dict[int, str]) -> Extraction:
    content, persona, concern = _fixture()
    return drop_ungrounded(
        extraction,
        answer=ANSWER,
        concern=concern,
        persona=persona,
        prior_answers=prior_answers,
        documents={
            SourceDocument.rfp_pws: content.rfp_text,
            SourceDocument.written_proposal: content.proposal_text,
        },
    )


def _run(
    extraction: Extraction,
    prior_claims: list[ClaimLedger],
    prior_answers: dict[int, str],
) -> Any:
    content, persona, concern = _fixture()
    return run_extraction(
        answer=ANSWER,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=prior_claims,
        prior_answers=prior_answers,
        client=FakeBedrockClient(extraction),  # type: ignore[arg-type]
    )


def test_flag_on_an_empty_history_is_dropped() -> None:
    """First scored turn of a session: nothing exists to contradict."""
    kept = _drop(_flagged(0), {})

    assert kept.consistency_flags == []


def test_flag_pointing_at_a_real_prior_turn_survives() -> None:
    kept = _drop(_flagged(1), _prior_answers(0, 1))

    assert [f.conflicts_with_turn for f in kept.consistency_flags] == [1]


def test_flag_naming_a_turn_with_no_stored_answer_is_dropped() -> None:
    """`conflicts_with_turn: 5` with only turns 0 and 1 stored names a turn with
    nothing recorded against it."""
    kept = _drop(_flagged(5), _prior_answers(0, 1))

    assert kept.consistency_flags == []


def test_real_and_bogus_flags_are_separated() -> None:
    kept = _drop(_flagged(0, 9), _prior_answers(0))

    assert [f.conflicts_with_turn for f in kept.consistency_flags] == [0]


def test_dropping_flags_leaves_every_other_field_alone() -> None:
    """The guard touches consistency_flags only — fact checks in particular, since
    a document conflict belongs there and must still score as `false_fact`."""
    extraction = Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=0,
                current_answer_span="bogus",
                prior_answer_span="bogus",
                acknowledged_revision=False,
            )
        ],
        fact_checks=[
            {  # type: ignore[list-item]
                "claim": "42 million records",
                "answer_span": "three named leads on day one",
                "source_document_id": "rfp_pws",
                "source_quote": "approximately 42 million records",
                "tier": 1,
                "verdict": "refuted",
            }
        ],
    )

    kept = _drop(extraction, {})

    assert kept.consistency_flags == []
    assert len(kept.fact_checks) == 1
    assert kept.fact_checks[0].claim == "42 million records"


def test_run_extraction_applies_the_guard() -> None:
    """End to end: a model flag naming a turn with no stored answer never reaches
    the scorer."""
    result = _run(_flagged(0), [], {})

    assert result.extraction.consistency_flags == []


def test_run_extraction_keeps_a_genuine_tier0_flag() -> None:
    result = _run(_flagged(0), _prior_claims(), _prior_answers(0))

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
