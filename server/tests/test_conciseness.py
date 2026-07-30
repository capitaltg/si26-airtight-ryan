from app.pipeline.conciseness import FILLER, compute_conciseness, count_words
from app.schemas.extraction import Extraction


def _extraction(*claim_types: str) -> Extraction:
    """Build an Extraction with one claim per given type. Non-commitment
    types need no backing; commitments require backing=bare."""
    claims = []
    for i, t in enumerate(claim_types):
        claim = {"text": f"claim {i}", "type": t, "span": f"span {i}"}
        if t == "commitment":
            claim["backing"] = "bare"
        claims.append(claim)
    return Extraction.model_validate({"claims": claims})


def test_empty_string_returns_all_zeros() -> None:
    result = compute_conciseness("", _extraction())
    assert result.word_count == 0
    assert result.filler_ratio == 0.0
    assert result.density == 0.0


def test_count_words_uses_whitespace_tokens() -> None:
    assert count_words("") == 0
    assert count_words(" \t\n ") == 0
    assert count_words("hello, 世界\nnext") == 3


def test_no_filler_gives_zero_ratio() -> None:
    result = compute_conciseness("We deliver the report on Monday", _extraction())
    assert result.word_count == 6
    assert result.filler_ratio == 0.0


def test_padded_sentence_gives_filler_ratio_above_zero() -> None:
    # "basically" and "actually" are in FILLER; 2 of 8 tokens.
    text = "Basically, we will actually deliver the report soon"
    result = compute_conciseness(text, _extraction())
    assert result.word_count == 8
    assert result.filler_ratio > 0.0
    assert result.filler_ratio == 2 / 8


def test_punctuation_attached_filler_still_counts() -> None:
    # Trailing comma must not stop "basically" from matching.
    result = compute_conciseness("Basically we shipped", _extraction())
    assert result.filler_ratio == 1 / 3


def test_density_is_substantive_claims_over_sentences() -> None:
    # 2 sentences; 2 substantive claims (empirical_checkable + commitment),
    # rhetorical and value_opinion excluded.
    text = "We shipped it. It runs well!"
    extraction = _extraction(
        "empirical_checkable", "commitment", "rhetorical", "value_opinion"
    )
    result = compute_conciseness(text, extraction)
    assert result.density == 2 / 2


def test_density_zero_when_no_sentences() -> None:
    # Text with no sentence-terminator and only whitespace segments.
    result = compute_conciseness("   ", _extraction("commitment"))
    assert result.density == 0.0


def test_filler_lexicon_is_lowercase_single_words() -> None:
    assert FILLER == frozenset(w.lower() for w in FILLER)
    assert all(" " not in w for w in FILLER)


def test_decimal_number_does_not_split_sentence() -> None:
    # "$1.2M" must not count as two sentences.
    text = "Cost is $1.2M total. We shipped it."
    result = compute_conciseness(text, _extraction("commitment", "commitment"))
    assert result.density == 2 / 2


def test_abbreviation_does_not_split_sentence() -> None:
    # "Inc." must not count as a sentence boundary.
    text = "Acme Inc. shipped the report. It runs well."
    result = compute_conciseness(text, _extraction("commitment"))
    assert result.density == 1 / 2


def test_conciseness_is_unchanged_by_whitespace_and_case_variants() -> None:
    # The score-side scaffolding must not move on a normalized-equal cache hit:
    # word_count via str.split(), the lowercased filler check, and density's
    # sentence split are already invariant to these variants.
    base = "Basically, we will actually deliver the report soon."
    whitespace_variant = "  Basically,  we will actually\tdeliver the report   soon.  \n"
    case_variant = "BASICALLY, WE WILL ACTUALLY DELIVER THE REPORT SOON."

    extraction = _extraction("commitment")
    base_result = compute_conciseness(base, extraction)
    whitespace_result = compute_conciseness(whitespace_variant, extraction)
    case_result = compute_conciseness(case_variant, extraction)

    for variant in (whitespace_result, case_result):
        assert variant.word_count == base_result.word_count
        assert variant.filler_ratio == base_result.filler_ratio
        assert variant.density == base_result.density
