"""A `contradiction` must be visible to the reaction, and must score exactly once.

Two defects found by replaying scenario-contradiction.json against the live
engine, both downstream of a correct extraction:

1. `_render_extraction_summary` dropped `consistency_flags`, so the reaction model
   was told "matched rows: contradiction" with no idea what was contradicted. It
   invented sources — an "org chart" and a "technical volume" that do not exist in
   the session — to justify a penalty it could see but not explain.
2. The model records a Tier-0 conflict as a `fact_check` with `tier: 0` as well as
   a `consistency_flag`. `score_turn` counts every refuted fact check, so one
   conflict scored `contradiction` -1 and `false_fact` -1.

See docs/issues/tier-0-contradiction-fires-on-document-conflicts.md.
"""

from app.content.loader import load_content
from app.pipeline.reaction import build_reaction_prompt
from app.pipeline.scoring import score_turn
from app.schemas.extraction import (
    Backing,
    Claim,
    ClaimType,
    ConsistencyFlag,
    Extraction,
    FactCheck,
    SourceDocument,
    Verdict,
)
from app.schemas.scoring import ScoreOutput


def _persona_concern() -> tuple[object, object]:
    content = load_content()
    return content.personas["technical_evaluator"], content.concerns["technical_approach"]


def _rubric() -> object:
    return load_content().rubric


_CURRENT_SPAN = "the migration squad is 6 people"
_PRIOR_SPAN = "a dedicated 14-person migration squad for the whole base period"


def test_reaction_prompt_shows_what_was_contradicted() -> None:
    """Without both spans the model has to invent a source for the penalty."""
    persona, concern = _persona_concern()
    extraction = Extraction(
        claims=[
            Claim(
                text="The migration squad is 6 people.",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="The migration squad is 6 people",
            )
        ],
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=0,
                current_answer_span=_CURRENT_SPAN,
                prior_answer_span=_PRIOR_SPAN,
                acknowledged_revision=False,
            )
        ],
    )

    prompt = build_reaction_prompt(
        persona=persona,  # type: ignore[arg-type]
        concern=concern,  # type: ignore[arg-type]
        extraction=extraction,
        score=ScoreOutput(support_delta=-1, matched_rows=["contradiction"], capped=False),
    )

    assert _CURRENT_SPAN in prompt
    assert _PRIOR_SPAN in prompt


def test_reaction_prompt_names_the_turn_that_was_contradicted() -> None:
    persona, concern = _persona_concern()
    extraction = Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=3,
                current_answer_span=_CURRENT_SPAN,
                prior_answer_span=_PRIOR_SPAN,
                acknowledged_revision=False,
            )
        ]
    )

    prompt = build_reaction_prompt(
        persona=persona,  # type: ignore[arg-type]
        concern=concern,  # type: ignore[arg-type]
        extraction=extraction,
        score=ScoreOutput(support_delta=-1, matched_rows=["contradiction"], capped=False),
    )

    assert "turn 3" in prompt


def test_reaction_prompt_stays_quiet_when_nothing_was_contradicted() -> None:
    """No flags means no contradiction section — the reply must not invent one."""
    persona, concern = _persona_concern()

    prompt = build_reaction_prompt(
        persona=persona,  # type: ignore[arg-type]
        concern=concern,  # type: ignore[arg-type]
        extraction=Extraction(),
        score=ScoreOutput(support_delta=1, matched_rows=["approach_cited"], capped=False),
    )

    assert "Contradicts" not in prompt


def test_tier0_fact_check_does_not_also_score_false_fact() -> None:
    """The Tier-0 conflict already scores as `contradiction`; counting the mirrored
    fact check as well charges the presenter twice for one statement."""
    extraction = Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=3,
                current_answer_span=_CURRENT_SPAN,
                prior_answer_span=_PRIOR_SPAN,
                acknowledged_revision=False,
            )
        ],
        fact_checks=[
            FactCheck(
                claim="Meridian rolls off after the first 30 days",
                answer_span="Meridian rolls off after the first 30 days",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="Turn 3 ledger: Meridian stays on through the entire 90 days",
                tier=0,
                verdict=Verdict.refuted,
            )
        ],
    )

    result = score_turn(extraction, _rubric())  # type: ignore[arg-type]

    assert "false_fact" not in result.matched_rows
    assert result.support_delta == -1


def test_tier1_fact_check_still_scores_false_fact() -> None:
    """A document refutation is what the row is for and must keep scoring."""
    extraction = Extraction(
        fact_checks=[
            FactCheck(
                claim="roughly 25 million case records",
                answer_span="roughly 25 million case records",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="PWS 3.1 states approximately 42 million records",
                tier=1,
                verdict=Verdict.refuted,
            )
        ]
    )

    result = score_turn(extraction, _rubric())  # type: ignore[arg-type]

    assert "false_fact" in result.matched_rows
    assert result.support_delta == -1


def test_a_tier0_and_a_tier1_refutation_score_one_false_fact_each_way() -> None:
    """Mixed case: the Tier-1 refutation counts, the Tier-0 mirror does not."""
    extraction = Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=1,
                current_answer_span=_CURRENT_SPAN,
                prior_answer_span=_PRIOR_SPAN,
                acknowledged_revision=False,
            )
        ],
        fact_checks=[
            FactCheck(
                claim="a",
                answer_span="a",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="Turn 1 ledger",
                tier=0,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="b",
                answer_span="b",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="PWS 3.1",
                tier=1,
                verdict=Verdict.refuted,
            ),
        ],
    )

    result = score_turn(extraction, _rubric())  # type: ignore[arg-type]

    # -1 contradiction, -1 for the single Tier-1 refutation
    assert result.support_delta == -2
    assert set(result.matched_rows) == {"contradiction", "false_fact"}
