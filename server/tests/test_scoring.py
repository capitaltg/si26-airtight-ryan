"""Exhaustive tests for the deterministic scoring engine (spec §6).

This is the moat: pure Python owns ``support_delta``, ``matched_rows``, and
``capped``. Every rubric row is covered here plus combinations, clamping, and the
sticky per-persona cap.
"""

from app.content.loader import load_content
from app.pipeline.scoring import apply_to_meter, score_turn
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    ConsistencyFlag,
    Dodge,
    DodgeType,
    Extraction,
    FactCheck,
    RedLineHit,
    RedLineSourceKind,
    SubQuestionCoverage,
    Verdict,
)


def _rubric():
    return load_content().rubric  # version 1, cap_ceiling 25


def _backed_claim() -> Claim:
    return Claim(
        text="PM has 12 yrs on comparable modernizations",
        type=ClaimType.commitment,
        backing=Backing.backed,
        span="our PM led three comparable case-management rollouts",
    )


# --- red line fires first ---------------------------------------------------


def test_red_line_fires_first_and_caps():
    ext = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="marcus_pws",
                source_kind=RedLineSourceKind.non_negotiable,
                span="we'll also do X outside scope",
                why="promised work outside the PWS",
            )
        ],
        # even a strong backed claim present:
        claims=[_backed_claim()],
    )
    out = score_turn(ext, _rubric())
    assert out.capped is True
    assert out.support_delta == -2
    assert out.matched_rows == ["red_line"]


# --- single rows ------------------------------------------------------------


def test_backed_commitment_scores_plus_two():
    ext = Extraction(claims=[_backed_claim()])
    out = score_turn(ext, _rubric())
    assert out.support_delta == 2
    assert out.matched_rows == ["evidence_backed"]
    assert out.capped is False


def test_dodge_scores_minus_two():
    ext = Extraction(
        dodges=[
            Dodge(
                sub_question_id="staffing",
                type=DodgeType.non_commitment,
                evidence="answered with enthusiasm but no name",
            )
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2
    assert out.matched_rows == ["dodge"]


def test_refuted_fact_scores_minus_one():
    ext = Extraction(
        fact_checks=[
            FactCheck(claim="we hold a GSA schedule", tier=1, verdict=Verdict.refuted, source="RFP")
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -1
    assert out.matched_rows == ["false_fact"]


def test_contradiction_scores_minus_one():
    ext = Extraction(
        consistency_flags=[
            ConsistencyFlag(conflicts_with_turn=2, detail="earlier said 3 leads, now 2")
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -1
    assert out.matched_rows == ["contradiction"]


def test_approach_cited_scores_plus_one():
    ext = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="tech_1", addressed=Addressed.full, span="we use event sourcing")
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 1
    assert out.matched_rows == ["approach_cited"]


def test_empty_extraction_is_unsubstantiated_zero():
    out = score_turn(Extraction(), _rubric())
    assert out.support_delta == 0
    assert out.matched_rows == ["unsubstantiated"]
    assert out.capped is False


# --- combinations & clamping ------------------------------------------------


def test_backed_beats_cited_no_double_count():
    # a backed commitment AND full coverage: evidence_backed fires, approach_cited
    # does not (not double-counted). Net +2.
    ext = Extraction(
        claims=[_backed_claim()],
        sub_question_coverage=[
            SubQuestionCoverage(id="tech_1", addressed=Addressed.full, span="event sourcing")
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 2
    assert out.matched_rows == ["evidence_backed"]


def test_cited_plus_contradiction_nets_zero():
    # +1 approach_cited AND -1 contradiction => net 0; both rows recorded.
    ext = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="tech_1", addressed=Addressed.partial, span="partial answer")
        ],
        consistency_flags=[ConsistencyFlag(conflicts_with_turn=1, detail="conflict")],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 0
    assert set(out.matched_rows) == {"approach_cited", "contradiction"}


def test_negatives_clamp_at_floor_minus_two():
    # dodge (-2) + refuted fact (-1) + contradiction (-1) = -4, clamps to -2.
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.deflection, evidence="e")],
        fact_checks=[FactCheck(claim="c", tier=1, verdict=Verdict.refuted, source="RFP")],
        consistency_flags=[ConsistencyFlag(conflicts_with_turn=1, detail="d")],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2


def test_multiple_refuted_facts_accumulate_before_clamp():
    ext = Extraction(
        fact_checks=[
            FactCheck(claim="a", tier=1, verdict=Verdict.refuted, source="RFP"),
            FactCheck(claim="b", tier=1, verdict=Verdict.refuted, source="RFP"),
            FactCheck(claim="c", tier=1, verdict=Verdict.supported, source="RFP"),
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2  # -1 + -1, supported ignored
    assert out.matched_rows == ["false_fact"]


def test_matched_rows_are_in_stable_rubric_order():
    # dodge + false_fact + contradiction should appear in rubric.yaml row order.
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.filibuster, evidence="e")],
        fact_checks=[FactCheck(claim="c", tier=1, verdict=Verdict.refuted, source="RFP")],
        consistency_flags=[ConsistencyFlag(conflicts_with_turn=1, detail="d")],
    )
    out = score_turn(ext, _rubric())
    assert out.matched_rows == ["dodge", "false_fact", "contradiction"]


def test_bare_commitment_is_not_evidence_backed():
    ext = Extraction(
        claims=[
            Claim(
                text="we'll staff it",
                type=ClaimType.commitment,
                backing=Backing.bare,
                span="we'll staff it",
            )
        ]
    )
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows
    assert out.support_delta == 0


# --- meter arithmetic -------------------------------------------------------


def test_cap_pins_meter_and_is_sticky():
    m, capped = apply_to_meter(68, -2, capped=True, cap_ceiling=25, already_capped=False)
    assert m == 25 and capped is True


def test_good_answer_after_cap_stays_capped():
    m, capped = apply_to_meter(25, +2, capped=False, cap_ceiling=25, already_capped=True)
    assert m == 25 and capped is True  # ceiling holds


def test_normal_gain_and_floor_clamp():
    assert apply_to_meter(50, +2, False, 25, False) == (52, False)
    assert apply_to_meter(1, -2, False, 25, False) == (0, False)


def test_ceiling_clamp_at_100():
    assert apply_to_meter(99, +2, False, 25, False) == (100, False)


def test_uncapped_meter_can_exceed_ceiling():
    # cap_ceiling only bites when sticky; an uncapped persona is unbounded by 25.
    m, capped = apply_to_meter(50, +2, capped=False, cap_ceiling=25, already_capped=False)
    assert m == 52 and capped is False
