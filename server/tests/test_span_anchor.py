"""Span re-anchoring: a replayed extraction must quote the answer on screen.

The response cache keys on a normalized answer, so a whitespace- or case-only
retype replays the extraction produced for the first phrasing. Those spans were
quoted out of that first text. These tests pin the guarantee that after
re-anchoring, every span is a real substring of the answer the presenter typed.
"""

from itertools import combinations

from app.bedrock.cache import normalize_answer
from app.pipeline.span_anchor import fold, reanchor_spans
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

RAW = "We follow a phased approach with a named PM. Our PM has 12 years of federal work."


def test_fold_is_public_and_collapses_case_and_whitespace() -> None:
    folded, origin = fold("  We   Staff\nThree  leads. ")
    assert folded == "we staff three leads."
    assert len(origin) == len(folded)
    # every origin index points at the character that produced it
    assert "  We   Staff\nThree  leads. "[origin[0]] == "W"


def _claim(span: str) -> Claim:
    return Claim(
        text="PM has 12 years of federal experience.",
        type=ClaimType.commitment,
        backing=Backing.backed,
        span=span,
    )


def test_verbatim_span_is_left_alone() -> None:
    extraction = Extraction(claims=[_claim("Our PM has 12 years of federal work")])
    result = reanchor_spans(extraction, RAW)
    assert result.claims[0].span == "Our PM has 12 years of federal work"


def test_case_variant_answer_gets_the_span_it_actually_contains() -> None:
    typed = "we follow a phased approach with a named pm. our pm HAS 12 years of federal work."
    extraction = Extraction(claims=[_claim("Our PM has 12 years of federal work")])
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].span == "our pm HAS 12 years of federal work"
    assert result.claims[0].span in typed


def test_whitespace_variant_answer_gets_the_span_it_actually_contains() -> None:
    typed = "We follow a phased approach with a named PM.  Our PM  has 12\tyears of federal work."
    extraction = Extraction(claims=[_claim("Our PM has 12 years of federal work")])
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].span == "Our PM  has 12\tyears of federal work"
    assert result.claims[0].span in typed


def test_mixed_whitespace_and_case_variant() -> None:
    typed = "  we follow a phased  approach with a named pm.\tour pm HAS 12 years of work. "
    extraction = Extraction(claims=[_claim("Our PM has 12 years of work")])
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].span in typed


def test_leading_and_trailing_whitespace_in_the_span_is_dropped() -> None:
    extraction = Extraction(claims=[_claim("  Our PM has 12 years of federal work  ")])
    result = reanchor_spans(extraction, RAW)
    assert result.claims[0].span == "Our PM has 12 years of federal work"


def test_unlocatable_span_is_left_unchanged_not_invented() -> None:
    extraction = Extraction(claims=[_claim("we will staff this with six architects")])
    result = reanchor_spans(extraction, RAW)
    assert result.claims[0].span == "we will staff this with six architects"


def test_empty_span_stays_empty() -> None:
    extraction = Extraction(claims=[_claim("")])
    result = reanchor_spans(extraction, RAW)
    assert result.claims[0].span == ""


def test_repeated_quote_anchors_to_the_first_occurrence() -> None:
    typed = "we ship weekly. and again: WE SHIP WEEKLY."
    extraction = Extraction(claims=[_claim("We ship weekly")])
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].span == "we ship weekly"


def test_every_span_bearing_field_is_reanchored() -> None:
    typed = "we follow a phased approach with a named pm. our pm HAS 12 years of federal work."
    extraction = Extraction(
        claims=[_claim("Our PM has 12 years of federal work")],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="sq1", addressed=Addressed.partial, span="We follow a phased approach"
            )
        ],
        dodges=[
            Dodge(
                sub_question_id="sq2",
                type=DodgeType.non_commitment,
                evidence="With a named PM",
            )
        ],
        red_line_hits=[
            RedLineHit(
                source_id="rl1",
                source_kind=RedLineSourceKind.concern_red_line,
                span="A Phased Approach",
                why="No dates given.",
            )
        ],
    )
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].span in typed
    assert result.sub_question_coverage[0].span in typed
    assert result.dodges[0].evidence in typed
    assert result.red_line_hits[0].span in typed


def test_any_span_from_a_normalized_equal_answer_can_be_anchored() -> None:
    """The invariant that makes replay safe: if two answers share a cache key they
    share a folded form, so a span quoted verbatim out of one is always locatable
    in the other. Every variant here keys equal to RAW, so none may fall through
    to the leave-unchanged branch.
    """
    variants = [
        RAW,
        f"   {RAW}  \n",
        RAW.replace(" ", "   "),
        RAW.replace(" ", "\t"),
        RAW.replace(". ", ".\n\n"),
        RAW.upper(),
        RAW.lower(),
        "  we FOLLOW a phased   approach with a NAMED pm.\tour pm HAS 12 years of federal work. ",
    ]
    quotes = [
        "We follow a phased approach",
        "Our PM has 12 years of federal work",
        "a named PM",
        "12 years",
    ]
    for variant in variants:
        for quote in quotes:
            assert normalize_answer(variant) == normalize_answer(RAW), variant
            extraction = Extraction(claims=[_claim(quote)])
            anchored = reanchor_spans(extraction, variant).claims[0].span
            assert anchored in variant, (variant, quote, anchored)


def test_whitespace_and_case_retypes_compose_freely() -> None:
    """Folding is closed over whitespace and case, so the safe retypes can be mixed
    in any combination and still land on one key. Every subset of the eight is
    checked, and each one must also yield a span that really occurs in it.
    """
    noise = [
        lambda s: f"   {s}  ",
        lambda s: s + "\n",
        lambda s: s.replace(" ", "  "),
        lambda s: s.replace(" ", "\t"),
        lambda s: s.replace(". ", ".\n"),
        lambda s: s.replace(". ", ".\n\n"),
        lambda s: s.upper(),
        lambda s: s.replace(" ", "\xa0"),
    ]
    quote = "Our PM has 12 years of federal work"
    for size in range(len(noise) + 1):
        for subset in combinations(noise, size):
            variant = RAW
            for edit in subset:
                variant = edit(variant)
            assert normalize_answer(variant) == normalize_answer(RAW), variant
            anchored = reanchor_spans(Extraction(claims=[_claim(quote)]), variant)
            assert anchored.claims[0].span in variant, variant


def test_one_content_change_poisons_any_amount_of_formatting_noise() -> None:
    """The other half of the property: formatting noise piled on top of a content
    edit must not fold back onto the original key."""
    noise = [
        lambda s: f"   {s}  ",
        lambda s: s.replace(" ", "  "),
        lambda s: s.replace(" ", "\t"),
        lambda s: s.upper(),
    ]
    edits = [
        lambda s: s.replace("phased approach", "phasedapproach"),
        lambda s: s.replace(". ", "."),
        lambda s: s.replace("phased", "phasd"),
        lambda s: s.replace("phased", "staged"),
    ]
    for edit in edits:
        for size in range(len(noise) + 1):
            for subset in combinations(noise, size):
                variant = edit(RAW)  # the content change goes first, so noise cannot erase it
                for add in subset:
                    variant = add(variant)
                assert normalize_answer(variant) != normalize_answer(RAW), variant


def test_words_run_together_cannot_be_anchored_and_are_left_alone() -> None:
    """A joined-word typo keys apart, so this span never actually reaches replay.
    Pinned anyway: the fold does not delete word boundaries, so the quote is not
    found and the span is returned untouched rather than approximated.
    """
    typed = "We follow a phased approach with a namedPM."
    extraction = Extraction(claims=[_claim("a named PM")])
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].span == "a named PM"
    assert normalize_answer(typed) != normalize_answer(RAW)


def test_null_coverage_span_stays_null() -> None:
    extraction = Extraction(
        sub_question_coverage=[SubQuestionCoverage(id="sq1", addressed=Addressed.none)]
    )
    result = reanchor_spans(extraction, RAW)
    assert result.sub_question_coverage[0].span is None


def test_prose_fields_are_not_touched() -> None:
    """Only quoted spans get re-anchored. Free-text reasons and restatements are
    the model's own words, so rewriting them against the answer would corrupt them."""
    typed = "we follow a phased approach with a named pm."
    extraction = Extraction(
        red_line_hits=[
            RedLineHit(
                source_id="rl1",
                source_kind=RedLineSourceKind.concern_red_line,
                span="a phased approach",
                why="We follow a phased approach with no dates attached.",
            )
        ],
        consistency_flags=[
            ConsistencyFlag(conflicts_with_turn=0, detail="We follow a phased approach, earlier.")
        ],
        fact_checks=[
            FactCheck(
                claim="We follow a phased approach",
                tier=1,
                verdict=Verdict.unverifiable,
                source="proposal",
            )
        ],
    )
    result = reanchor_spans(extraction, typed)
    assert result.red_line_hits[0].why == "We follow a phased approach with no dates attached."
    assert result.consistency_flags[0].detail == "We follow a phased approach, earlier."
    assert result.fact_checks[0].claim == "We follow a phased approach"


def test_scored_signals_are_untouched() -> None:
    """Re-anchoring rewrites quote text only. The fields the scorer reads (claim
    type and backing, coverage verdict, dodge type) must come through identical,
    so the score cannot move."""
    typed = "OUR PM HAS 12 YEARS OF FEDERAL WORK."
    extraction = Extraction(
        claims=[_claim("Our PM has 12 years of federal work")],
        sub_question_coverage=[
            SubQuestionCoverage(id="sq1", addressed=Addressed.full, span="Our PM")
        ],
        dodges=[
            Dodge(sub_question_id="sq2", type=DodgeType.deflection, evidence="Our PM"),
        ],
    )
    result = reanchor_spans(extraction, typed)
    assert result.claims[0].type is ClaimType.commitment
    assert result.claims[0].backing is Backing.backed
    assert result.claims[0].text == extraction.claims[0].text
    assert result.sub_question_coverage[0].addressed is Addressed.full
    assert result.sub_question_coverage[0].id == "sq1"
    assert result.dodges[0].type is DodgeType.deflection
    assert result.dodges[0].sub_question_id == "sq2"
