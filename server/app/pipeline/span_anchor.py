"""Re-anchor model-quoted spans onto the answer the presenter actually typed.

The response cache keys on a normalized answer (see
``app.bedrock.cache.normalize_answer``), so a whitespace- or case-only retype
replays the extraction that was produced for the first phrasing. Those spans were
quoted verbatim out of that first text, so replaying them as-is puts a quote in
the transcript and the after-action report that does not occur in the answer on
screen. ``Claim.span`` is documented as a verbatim quote and
``report.ScoredFinding`` requires one, so each replayed span is mapped back onto
the current text here.

Pure code, no model call. It only ever returns a substring of the answer, takes
the first match when a quote occurs more than once, and leaves a span alone when
it cannot be located rather than inventing one. Only quoted fields are rewritten;
free-text reasons and claim restatements are the model's own words and are left
as emitted. Nothing the scorer reads is touched, so the score cannot move.
"""

from __future__ import annotations

from app.schemas.extraction import Extraction


def _fold(text: str) -> tuple[str, list[int]]:
    """Lowercased, whitespace-collapsed ``text`` plus the source index of each
    character kept.

    ``origin[i]`` is the index in ``text`` that produced ``folded[i]``, which is
    what lets a match in folded space be sliced back out of the raw text. A run of
    whitespace folds to one space mapped to the run's first character; leading and
    trailing runs are dropped. A character whose ``lower()`` is not one character
    (a handful of Unicode cases) is kept as-is, because substituting a
    different-length form would misalign every later index.
    """
    folded: list[str] = []
    origin: list[int] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            run_start = i
            while i < n and text[i].isspace():
                i += 1
            if folded:  # a leading run contributes nothing
                folded.append(" ")
                origin.append(run_start)
            continue
        lowered = text[i].lower()
        folded.append(lowered if len(lowered) == 1 else text[i])
        origin.append(i)
        i += 1
    if folded and folded[-1] == " ":  # a trailing run left a dangling space
        folded.pop()
        origin.pop()
    return "".join(folded), origin


def _anchor(span: str, answer: str, folded_answer: str, origin: list[int]) -> str:
    """The substring of ``answer`` that ``span`` quotes, or ``span`` unchanged."""
    if span and span in answer:
        return span
    needle, _ = _fold(span)
    if not needle:
        return span
    at = folded_answer.find(needle)
    if at == -1:
        return span
    return answer[origin[at] : origin[at + len(needle) - 1] + 1]


def reanchor_spans(extraction: Extraction, answer: str) -> Extraction:
    """Rewrite every quoted span in ``extraction`` to the text ``answer`` holds.

    A no-op on the cold path: a span the model just quoted out of ``answer`` is
    already a substring, so it short-circuits. The rewrite only bites on a
    normalized cache hit, where the span came from an earlier phrasing.
    """
    folded_answer, origin = _fold(answer)

    def fix(span: str | None) -> str | None:
        if span is None:
            return None
        return _anchor(span, answer, folded_answer, origin)

    return extraction.model_copy(
        update={
            "claims": [c.model_copy(update={"span": fix(c.span)}) for c in extraction.claims],
            "sub_question_coverage": [
                cov.model_copy(update={"span": fix(cov.span)})
                for cov in extraction.sub_question_coverage
            ],
            "dodges": [
                d.model_copy(update={"evidence": fix(d.evidence)}) for d in extraction.dodges
            ],
            "red_line_hits": [
                h.model_copy(update={"span": fix(h.span)}) for h in extraction.red_line_hits
            ],
        }
    )
