"""Exhaustive tests for the deterministic scoring engine (spec §6).

This is the moat: pure Python owns ``support_delta``, ``matched_rows``, and
``capped``. Every rubric row is covered here plus combinations, clamping, and the
sticky per-persona cap.
"""

from app.content.loader import load_content
from app.pipeline.scoring import apply_limit_penalty, apply_to_meter, score_turn
from app.schemas.content import Rubric, RubricRow
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
    SourceDocument,
    SubQuestionCoverage,
    Verdict,
)
from app.schemas.scoring import LimitKind, LimitMeasurement, LimitResult, ScoreOutput


def _rubric():
    return load_content().rubric  # version 1, cap_ceiling 25


def _backed_claim() -> Claim:
    return Claim(
        text="PM has 12 yrs on comparable modernizations",
        type=ClaimType.commitment,
        backing=Backing.backed,
        span="our PM led three comparable case-management rollouts",
    )


def _refuted_check() -> FactCheck:
    return FactCheck(
        claim="PM has eighteen years",
        answer_span="eighteen years",
        source_document_id=SourceDocument.written_proposal,
        source_quote="twelve years managing federal software programs",
        tier=1,
        verdict=Verdict.refuted,
    )


def _hidden_flag() -> ConsistencyFlag:
    return ConsistencyFlag(
        conflicts_with_turn=1,
        current_answer_span="region by region over three weeks",
        prior_answer_span="a single weekend maintenance window",
        acknowledged_revision=False,
    )


def _revision_flag() -> ConsistencyFlag:
    return ConsistencyFlag(
        conflicts_with_turn=1,
        current_answer_span="our top risk now is staffing ramp-up",
        prior_answer_span="the biggest risk is data-migration integrity",
        acknowledged_revision=True,
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
                answer_span="answered with enthusiasm but no name",
            )
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2
    assert out.matched_rows == ["dodge"]


def test_refuted_fact_scores_minus_one():
    ext = Extraction(
        fact_checks=[
            FactCheck(
                claim="we hold a GSA schedule",
                answer_span="we hold a GSA schedule",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            )
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -1
    assert out.matched_rows == ["false_fact"]


def test_contradiction_scores_minus_one():
    ext = Extraction(
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=2,
                current_answer_span="earlier said 3 leads, now 2",
                prior_answer_span="earlier said 3 leads, now 2",
                acknowledged_revision=False,
            )
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


def test_over_limit_penalty_is_once_and_strictly_above_limit():
    extraction = Extraction()
    semantic = score_turn(extraction, _rubric())
    exact = apply_limit_penalty(
        semantic,
        _rubric(),
        LimitMeasurement(
            kind=LimitKind.text_words,
            measured=300,
            warning_threshold=225,
            limit_threshold=300,
        ),
    )
    over = apply_limit_penalty(
        semantic,
        _rubric(),
        LimitMeasurement(
            kind=LimitKind.text_words,
            measured=301,
            warning_threshold=225,
            limit_threshold=300,
        ),
    )

    assert exact.limit is not None and not exact.limit.penalty_applied
    assert "over_limit" not in exact.matched_rows
    assert over.support_delta == -1
    assert over.limit is not None and over.limit.penalty_applied
    assert over.matched_rows == ["unsubstantiated", "over_limit"]


def test_over_limit_penalty_stacks_below_semantic_floor():
    semantic = score_turn(
        Extraction(
            dodges=[
                Dodge(
                    sub_question_id="staffing",
                    type=DodgeType.non_commitment,
                    answer_span="answered with enthusiasm but no name",
                )
            ]
        ),
        _rubric(),
    )
    final = apply_limit_penalty(
        semantic,
        _rubric(),
        LimitMeasurement(
            kind=LimitKind.text_words,
            measured=301,
            warning_threshold=225,
            limit_threshold=300,
        ),
    )

    assert semantic.support_delta == -2
    assert final.support_delta == -3
    assert final.matched_rows == ["dodge", "over_limit"]


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
    # -1 contradiction + 1 approach_cited = 0 by sum, and the ceiling holds it
    # at 0 regardless; both rows recorded.
    ext = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="tech_1", addressed=Addressed.partial, span="partial answer")
        ],
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=1,
                current_answer_span="conflict",
                prior_answer_span="conflict",
                acknowledged_revision=False,
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 0
    assert set(out.matched_rows) == {"approach_cited", "contradiction"}


def test_negatives_clamp_at_floor_minus_two():
    # dodge (-2) + refuted fact (-1) + contradiction (-1) = -4, clamps to -2.
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.deflection, answer_span="e")],
        fact_checks=[
            FactCheck(
                claim="c",
                answer_span="c",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            )
        ],
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=1,
                current_answer_span="d",
                prior_answer_span="d",
                acknowledged_revision=False,
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2


def test_multiple_refuted_facts_accumulate_before_clamp():
    ext = Extraction(
        fact_checks=[
            FactCheck(
                claim="a",
                answer_span="a",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="b",
                answer_span="b",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="c",
                answer_span="c",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.supported,
            ),
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2  # -1 + -1, supported ignored
    assert out.matched_rows == ["false_fact"]


def test_row_counts_report_false_fact_applications():
    ext = Extraction(
        fact_checks=[
            FactCheck(
                claim="a",
                answer_span="a",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="b",
                answer_span="b",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="c",
                answer_span="c",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.supported,
            ),
        ]
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2
    assert out.raw_support_delta == -2
    assert out.row_counts == {"false_fact": 2}


def test_raw_support_delta_keeps_the_points_the_clamp_absorbed():
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.deflection, answer_span="e")],
        fact_checks=[
            FactCheck(
                claim="a",
                answer_span="a",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="b",
                answer_span="b",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
            FactCheck(
                claim="c",
                answer_span="c",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            ),
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2
    assert out.raw_support_delta == -5
    assert out.row_counts == {"dodge": 1, "false_fact": 3}


def test_single_dodge_sits_at_the_bound_without_clamping():
    out = score_turn(
        Extraction(dodges=[Dodge(sub_question_id="s", type=DodgeType.deflection, answer_span="e")]),
        _rubric(),
    )
    assert out.support_delta == out.raw_support_delta == -2
    assert out.row_counts == {"dodge": 1}


def test_red_line_counts_once_however_many_hits():
    hit = RedLineHit(
        source_id="technical_approach",
        source_kind=RedLineSourceKind.concern_red_line,
        span="on-premises in our own data center",
        why="PWS 3.1 forbids on-premises hosting",
    )
    out = score_turn(Extraction(red_line_hits=[hit, hit, hit]), _rubric())
    assert out.matched_rows == ["red_line"]
    assert out.row_counts == {"red_line": 1}
    assert out.raw_support_delta == -2


def test_unsubstantiated_turn_has_a_zero_raw_delta():
    out = score_turn(Extraction(), _rubric())
    assert out.matched_rows == ["unsubstantiated"]
    assert out.row_counts == {"unsubstantiated": 1}
    assert out.raw_support_delta == 0


def test_row_counts_ordering_follows_matched_rows():
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.filibuster, answer_span="e")],
        fact_checks=[
            FactCheck(
                claim="c",
                answer_span="c",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            )
        ],
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=1,
                current_answer_span="d",
                prior_answer_span="d",
                acknowledged_revision=False,
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert list(out.row_counts) == out.matched_rows == ["dodge", "false_fact", "contradiction"]


def test_legacy_score_json_backfills_both_new_fields():
    legacy = ScoreOutput(support_delta=-1, matched_rows=["dodge"])
    assert legacy.row_counts == {"dodge": 1}
    assert legacy.raw_support_delta == -1


def test_legacy_over_limit_row_reconstructs_the_semantic_delta():
    legacy = ScoreOutput(
        support_delta=-3,
        matched_rows=["dodge", "over_limit"],
        limit=LimitResult(
            kind=LimitKind.text_words,
            measured=301,
            warning_threshold=225,
            limit_threshold=300,
            exceeded=True,
            penalty_applied=True,
            penalty_value=-1,
        ),
    )
    assert legacy.raw_support_delta == -2


def test_row_counts_keys_outside_matched_rows_are_dropped():
    out = ScoreOutput(
        support_delta=-1,
        matched_rows=["dodge"],
        row_counts={"dodge": 1, "false_fact": 4},
    )
    assert out.row_counts == {"dodge": 1}


def test_limit_penalty_preserves_counts_and_the_raw_delta():
    semantic = score_turn(
        Extraction(
            fact_checks=[
                FactCheck(
                    claim="a",
                    answer_span="a",
                    source_document_id=SourceDocument.rfp_pws,
                    source_quote="RFP",
                    tier=1,
                    verdict=Verdict.refuted,
                ),
                FactCheck(
                    claim="b",
                    answer_span="b",
                    source_document_id=SourceDocument.rfp_pws,
                    source_quote="RFP",
                    tier=1,
                    verdict=Verdict.refuted,
                ),
            ]
        ),
        _rubric(),
    )
    final = apply_limit_penalty(
        semantic,
        _rubric(),
        LimitMeasurement(
            kind=LimitKind.text_words,
            measured=301,
            warning_threshold=225,
            limit_threshold=300,
        ),
    )
    assert final.support_delta == -3
    assert final.raw_support_delta == -2
    assert final.row_counts == {"false_fact": 2, "over_limit": 1}
    assert list(final.row_counts) == final.matched_rows


def test_matched_rows_are_in_stable_rubric_order():
    # dodge + false_fact + contradiction should appear in rubric.yaml row order.
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.filibuster, answer_span="e")],
        fact_checks=[
            FactCheck(
                claim="c",
                answer_span="c",
                source_document_id=SourceDocument.rfp_pws,
                source_quote="RFP",
                tier=1,
                verdict=Verdict.refuted,
            )
        ],
        consistency_flags=[
            ConsistencyFlag(
                conflicts_with_turn=1,
                current_answer_span="d",
                prior_answer_span="d",
                acknowledged_revision=False,
            )
        ],
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


# --- the integrity ceiling --------------------------------------------------


def test_false_fact_ceilings_a_backed_answer_at_zero():
    # -1 false_fact + 2 evidence_backed = +1 before the ceiling, 0 after.
    ext = Extraction(claims=[_backed_claim()], fact_checks=[_refuted_check()])
    out = score_turn(ext, _rubric())
    assert out.support_delta == 0
    assert out.raw_support_delta == 1
    assert out.integrity_ceiling is True
    assert out.matched_rows == ["false_fact", "evidence_backed"]
    assert out.capped is False  # the ceiling is not the red-line meter pin


def test_hidden_contradiction_ceilings_a_backed_answer_at_zero():
    ext = Extraction(claims=[_backed_claim()], consistency_flags=[_hidden_flag()])
    out = score_turn(ext, _rubric())
    assert out.support_delta == 0
    assert out.raw_support_delta == 1
    assert out.integrity_ceiling is True
    assert out.matched_rows == ["contradiction", "evidence_backed"]


def test_the_ceiling_never_lifts_a_negative_delta():
    # dodge (-2) + false fact (-1) = -3, clamps to -2; a 0 ceiling must not raise it.
    ext = Extraction(
        dodges=[Dodge(sub_question_id="s", type=DodgeType.deflection, answer_span="e")],
        fact_checks=[_refuted_check()],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2
    # nothing was withheld, so the report has no subtraction to explain
    assert out.integrity_ceiling is False


def test_the_ceiling_applies_before_the_over_limit_penalty():
    ext = Extraction(claims=[_backed_claim()], fact_checks=[_refuted_check()])
    scored = score_turn(ext, _rubric())
    out = apply_limit_penalty(
        scored,
        _rubric(),
        LimitMeasurement(
            kind=LimitKind.text_words, measured=210, warning_threshold=150, limit_threshold=200
        ),
    )
    assert out.support_delta == -1  # 0 after the ceiling, then -1 for length
    assert out.integrity_ceiling is True


def test_a_red_line_ignores_the_ceiling_entirely():
    ext = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="marcus_pws",
                source_kind=RedLineSourceKind.non_negotiable,
                span="we'll also do X outside scope",
                why="promised work outside the PWS",
            )
        ],
        fact_checks=[_refuted_check()],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == -2
    assert out.capped is True
    assert out.matched_rows == ["red_line"]
    assert out.integrity_ceiling is False


# --- acknowledged revision --------------------------------------------------


def test_an_acknowledged_revision_scores_zero_on_its_own_row():
    ext = Extraction(consistency_flags=[_revision_flag()])
    out = score_turn(ext, _rubric())
    assert out.support_delta == 0
    # its own row, not `unsubstantiated`: the report must name what happened
    assert out.matched_rows == ["acknowledged_revision"]
    assert out.integrity_ceiling is False


def test_an_acknowledged_revision_does_not_ceiling_positive_rows():
    ext = Extraction(claims=[_backed_claim()], consistency_flags=[_revision_flag()])
    out = score_turn(ext, _rubric())
    assert out.support_delta == 2
    assert out.integrity_ceiling is False
    assert out.matched_rows == ["acknowledged_revision", "evidence_backed"]


def test_archived_score_json_without_the_new_field_still_validates():
    # Sessions scored before v4 have no `integrity_ceiling` key. They must load,
    # because the report re-derives every archived turn (see the spec, §4).
    legacy = ScoreOutput(support_delta=-1, matched_rows=["contradiction"])
    assert legacy.integrity_ceiling is False


def test_one_honest_revision_does_not_cover_a_hidden_flip():
    ext = Extraction(
        claims=[_backed_claim()],
        consistency_flags=[_hidden_flag(), _revision_flag()],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 0  # -1 + 2 = +1, ceilinged to 0
    assert out.integrity_ceiling is True
    assert out.matched_rows == ["contradiction", "acknowledged_revision", "evidence_backed"]


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


def test_cap_ceiling_derives_from_the_red_line_row():
    rubric = _rubric()
    # The computed ceiling equals the red_line row's inline cap.
    red_line = next(r for r in rubric.rows if r.id == "red_line")
    assert red_line.cap == 25
    assert rubric.cap_ceiling == 25


def test_cap_ceiling_falls_back_to_100_when_no_row_caps():
    rubric = Rubric(
        version=1,
        rows=[RubricRow(id="dodge", description="d", support_value=-2)],
    )
    assert rubric.cap_ceiling == 100
    # With no ceiling, a sticky-capped meter is still bounded only by 100.
    meter, capped = apply_to_meter(
        80, +2, capped=True, cap_ceiling=rubric.cap_ceiling, already_capped=False
    )
    assert (meter, capped) == (82, True)


# --- verified empirical evidence ------------------------------------------------


def _supported_check(answer_span: str) -> FactCheck:
    return FactCheck(
        claim="comparable-scale migration on the record",
        answer_span=answer_span,
        source_document_id=SourceDocument.written_proposal,
        source_quote="1.8 million cases migrated with zero data loss",
        tier=1,
        verdict=Verdict.supported,
    )


def test_a_document_confirmed_empirical_claim_is_evidence_backed() -> None:
    ext = Extraction(
        claims=[
            Claim(
                text="migrated a 1.8M-case system with zero data loss",
                type=ClaimType.empirical_checkable,
                span="we migrated a 1.8-million-case system with zero data loss",
            )
        ],
        fact_checks=[_supported_check("we migrated a 1.8-million-case system")],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="comparable_scale",
                addressed=Addressed.full,
                span="a 1.8-million-case system",
                evidence_claim_spans=["we migrated a 1.8-million-case system with zero data loss"],
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 2
    assert out.matched_rows == ["evidence_backed"]  # approach_cited still suppressed


def test_an_unconfirmed_empirical_claim_is_only_approach_cited() -> None:
    ext = Extraction(
        claims=[
            Claim(
                text="migrated a 1.8M-case system",
                type=ClaimType.empirical_checkable,
                span="we migrated a 1.8-million-case system",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="comparable_scale",
                addressed=Addressed.full,
                span="a 1.8-million-case system",
                evidence_claim_spans=["we migrated a 1.8-million-case system"],
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert out.support_delta == 1
    assert out.matched_rows == ["approach_cited"]


def test_a_supported_check_with_no_empirical_claim_behind_it_is_not_backed() -> None:
    # The row rewards a verified CLAIM, not a stray check. Nothing to attach to.
    ext = Extraction(fact_checks=[_supported_check("we migrated a system")])
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows
    assert out.matched_rows == ["unsubstantiated"]


def test_a_tier_zero_supported_check_does_not_back_a_claim() -> None:
    ext = Extraction(
        claims=[
            Claim(
                text="migrated a 1.8M-case system",
                type=ClaimType.empirical_checkable,
                span="we migrated a 1.8-million-case system",
            )
        ],
        fact_checks=[
            FactCheck(
                claim="c",
                answer_span="we migrated a 1.8-million-case system",
                source_document_id=SourceDocument.written_proposal,
                source_quote="q",
                tier=0,
                verdict=Verdict.supported,
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows


def test_a_narrower_unconfirmed_claim_riding_a_wider_confirmed_span_is_not_backed() -> None:
    # The claim's own span is never confirmed; it merely sits inside a wider,
    # unrelated check's answer_span. Only the check's answer_span being found
    # inside the claim's span counts as confirmation, never the reverse.
    ext = Extraction(
        claims=[
            Claim(
                text="we will also rebuild the payments engine",
                type=ClaimType.empirical_checkable,
                span="we will also rebuild the payments engine",
            )
        ],
        fact_checks=[
            _supported_check(
                "we migrated 1.8 million cases and we will also rebuild the payments engine"
            )
        ],
    )
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows
    assert out.matched_rows == ["unsubstantiated"]


def test_a_confirmed_commitment_claim_alone_is_not_the_empirical_path() -> None:
    # The empirical path is for `empirical_checkable`. A commitment still needs
    # `backing == backed`; a supported check does not substitute for it.
    ext = Extraction(
        claims=[
            Claim(
                text="we commit to 90 days",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="we complete transition-in within 90 calendar days",
            )
        ],
        fact_checks=[_supported_check("we complete transition-in within 90 calendar days")],
    )
    out = score_turn(ext, _rubric())
    assert "evidence_backed" not in out.matched_rows
