"""The authored `requires` contract, enforced in pure code.

`SubQuestion.requires` used to reach the prompt and stop there. These tests pin
what it now changes: a coverage row keeps its degree only when an unrefuted claim
of the required type is linked to it.
"""

from app.pipeline.coverage_contract import enforce_requires
from app.schemas.content import Concern, Requires, SubQuestion
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    Extraction,
    FactCheck,
    SourceDocument,
    SubQuestionCoverage,
    Verdict,
)


def _concern(requires: Requires) -> Concern:
    return Concern(
        concern_id="key_personnel",
        core_ask="Tell us about the PM.",
        sub_questions=[SubQuestion(id="pm", text="Who is the PM?", requires=requires)],
        red_lines=[],
        what_would_satisfy="A named, qualified, committed PM.",
    )


def _covered(links: list[str]) -> SubQuestionCoverage:
    return SubQuestionCoverage(
        id="pm",
        addressed=Addressed.full,
        span="Karen Holloway",
        evidence_claim_spans=links,
    )


def _claim(kind: ClaimType, span: str, backing: Backing | None = None) -> Claim:
    return Claim(text="restated", type=kind, backing=backing, span=span)


def test_commitment_requirement_met_by_a_commitment_claim() -> None:
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.commitment, "she is full-time", Backing.bare)],
            sub_question_coverage=[_covered(["she is full-time"])],
        ),
        _concern(Requires.commitment),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.full


def test_commitment_requirement_not_met_by_an_empirical_claim() -> None:
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.empirical_checkable, "she has twelve years")],
            sub_question_coverage=[_covered(["she has twelve years"])],
        ),
        _concern(Requires.commitment),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_fact_requirement_not_met_by_a_commitment_claim() -> None:
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.commitment, "she is full-time", Backing.bare)],
            sub_question_coverage=[_covered(["she is full-time"])],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_either_requirement_accepts_a_fact_and_a_commitment() -> None:
    for kind, backing in (
        (ClaimType.empirical_checkable, None),
        (ClaimType.commitment, Backing.bare),
    ):
        out = enforce_requires(
            Extraction(
                claims=[_claim(kind, "she has twelve years", backing)],
                sub_question_coverage=[_covered(["she has twelve years"])],
            ),
            _concern(Requires.fact_or_commitment),
        )
        assert out.sub_question_coverage[0].addressed is Addressed.full


def test_rhetorical_and_value_claims_satisfy_nothing() -> None:
    for kind in (ClaimType.rhetorical, ClaimType.value_opinion):
        out = enforce_requires(
            Extraction(
                claims=[_claim(kind, "our people love the mission")],
                sub_question_coverage=[_covered(["our people love the mission"])],
            ),
            _concern(Requires.fact_or_commitment),
        )
        assert out.sub_question_coverage[0].addressed is Addressed.none


def test_coverage_with_no_links_is_demoted() -> None:
    out = enforce_requires(
        Extraction(sub_question_coverage=[_covered([])]),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_a_refuted_claim_does_not_satisfy_the_contract() -> None:
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.empirical_checkable, "eighteen years")],
            sub_question_coverage=[_covered(["eighteen years"])],
            fact_checks=[
                FactCheck(
                    claim="PM has eighteen years",
                    answer_span="eighteen years",
                    source_document_id=SourceDocument.written_proposal,
                    source_quote="twelve years",
                    tier=1,
                    verdict=Verdict.refuted,
                )
            ],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_a_tier_zero_refutation_does_not_disqualify_a_claim() -> None:
    # Tier 0 is a self-contradiction, which the `contradiction` row already
    # charges. It is not a document proving the claim false.
    out = enforce_requires(
        Extraction(
            claims=[_claim(ClaimType.empirical_checkable, "eighteen years")],
            sub_question_coverage=[_covered(["eighteen years"])],
            fact_checks=[
                FactCheck(
                    claim="PM has eighteen years",
                    answer_span="eighteen years",
                    source_document_id=SourceDocument.written_proposal,
                    source_quote="twelve years",
                    tier=0,
                    verdict=Verdict.refuted,
                )
            ],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.full


def test_partial_keeps_its_degree_when_the_contract_is_met() -> None:
    # Demotion is binary on the evidence type. The model still owns the degree.
    extraction = Extraction(
        claims=[_claim(ClaimType.empirical_checkable, "she has twelve years")],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm",
                addressed=Addressed.partial,
                span="twelve years",
                evidence_claim_spans=["she has twelve years"],
            )
        ],
    )
    out = enforce_requires(extraction, _concern(Requires.fact))
    assert out.sub_question_coverage[0].addressed is Addressed.partial


def test_a_link_naming_a_wrong_type_claim_does_not_ride_a_narrower_right_type_claim() -> None:
    # The link exactly names claim A (rhetorical), which satisfies nothing. A
    # different, right-type claim B happens to sit textually inside that same
    # link (a coincidental substring), but the link never names B specifically
    # — only a one-directional containment (link inside a claim's span, never a
    # claim's span merely found inside the link) should count as naming a
    # claim, matching grounding.py's `_links_a_claim` convention. Bidirectional
    # matching would wrongly let claim B's narrower span "overlap" the wider
    # link and satisfy the contract.
    out = enforce_requires(
        Extraction(
            claims=[
                _claim(
                    ClaimType.rhetorical,
                    "We take risk seriously and we run on GovCloud",
                ),
                _claim(ClaimType.empirical_checkable, "we run on GovCloud"),
            ],
            sub_question_coverage=[
                _covered(["We take risk seriously and we run on GovCloud"])
            ],
        ),
        _concern(Requires.fact),
    )
    assert out.sub_question_coverage[0].addressed is Addressed.none


def test_an_already_none_row_and_an_unchanged_extraction_pass_through() -> None:
    extraction = Extraction(
        sub_question_coverage=[
            SubQuestionCoverage(id="pm", addressed=Addressed.none, span=None)
        ]
    )
    assert enforce_requires(extraction, _concern(Requires.fact)) is extraction
