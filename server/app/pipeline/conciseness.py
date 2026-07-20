"""Conciseness signals computed in pure code (issue #4).

These numbers are NEVER emitted by the model — they are derived from the
answer text and the validated ``Extraction`` and attached afterward, so the
scorer only ever sees code-owned values. See ``schemas.extraction`` for why
``Conciseness`` is not a field on the tool schema.

The filler lexicon is single-word only: tokenization is whitespace-based, so a
multi-word phrase like "you know" could never match a single token. Keeping the
set single-word keeps the ratio honest rather than silently never-matching.
"""

import re

from app.schemas.extraction import ClaimType, Conciseness, Extraction

FILLER: frozenset[str] = frozenset(
    {
        "um",
        "uh",
        "basically",
        "honestly",
        "actually",
        "literally",
        "essentially",
        "really",
        "just",
        "very",
        "simply",
    }
)

# Claim types that do NOT count toward substantive density.
_NON_SUBSTANTIVE: frozenset[ClaimType] = frozenset(
    {ClaimType.rhetorical, ClaimType.value_opinion}
)

_SENTENCE_END = re.compile(r"[.!?]")
_STRIP = ".,;:!?\"'()[]{}"

# Trailing abbreviations that a '.' does not end a sentence after. Acronyms
# with internal periods ("U.S.", "e.g.") still over-split on their first dot
# ("U" + "." + "S.") -- this is a word-level heuristic, not a real tokenizer.
_ABBREVIATIONS: frozenset[str] = frozenset(
    {"mr", "mrs", "ms", "dr", "jr", "sr", "st", "vs", "etc", "inc", "corp", "ltd", "co"}
)
_TRAILING_WORD = re.compile(r"([A-Za-z]+)$")


def _is_decimal_point(text: str, idx: int) -> bool:
    before, after = text[:idx], text[idx + 1 :]
    return bool(before) and before[-1].isdigit() and bool(after) and after[0].isdigit()


def _is_abbreviation(before: str) -> bool:
    match = _TRAILING_WORD.search(before)
    return match is not None and match.group(1).lower() in _ABBREVIATIONS


def _split_sentences(text: str) -> list[str]:
    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        idx = match.start()
        if match.group() == "." and (_is_decimal_point(text, idx) or _is_abbreviation(text[:idx])):
            continue
        sentences.append(text[start:idx])
        start = idx + 1
    sentences.append(text[start:])
    return [s for s in sentences if s.strip()]


def compute_conciseness(answer_text: str, extraction: Extraction) -> Conciseness:
    tokens = answer_text.split()
    word_count = len(tokens)

    if word_count:
        filler_hits = sum(1 for t in tokens if t.strip(_STRIP).lower() in FILLER)
        filler_ratio = filler_hits / word_count
    else:
        filler_ratio = 0.0

    sentences = _split_sentences(answer_text)
    substantive = sum(
        1 for c in extraction.claims if c.type not in _NON_SUBSTANTIVE
    )
    density = substantive / len(sentences) if sentences else 0.0

    return Conciseness(
        word_count=word_count,
        filler_ratio=filler_ratio,
        density=density,
    )
