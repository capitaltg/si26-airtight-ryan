"""Discard model findings the answer does not support, before the scorer sees them.

``Claim.span``, ``RedLineHit.span`` and ``SubQuestionCoverage.span`` are all
documented as verbatim quotes from the answer, and ``Claim.span`` says outright
that a claim without one does not count. Nothing enforced that. A fabricated
span on a red-line hit bills -2 and pins the persona's meter at the cap,
stickily and forever, on the model's word alone.

Pure code, no model call, no I/O. It only ever removes; it never rewrites a
field and never raises. Runs after ``span_anchor.reanchor_spans`` so a replayed
span is mapped onto the current phrasing before the membership test — reversed,
a whitespace-only retype would discard legitimate findings. ``RedLineHit.source_id``
is also validated against the authored ids of its ``source_kind``.

``fact_checks`` is deliberately untouched here: ``FactCheck.claim`` is a model
restatement rather than a quote, and verifying ``answer_span``/``source_quote``
against the answer and the named ``source_document_id`` is added in a later
task. See the spec's out-of-scope section.
"""

from __future__ import annotations

import logging

from app.pipeline.span_anchor import fold
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Addressed, Extraction, RedLineSourceKind

logger = logging.getLogger(__name__)


def _is_quoted(span: str | None, folded_answer: str) -> bool:
    """True when ``span`` occurs in the answer, ignoring case and whitespace runs."""
    if not span:
        return False
    needle, _ = fold(span)
    return bool(needle) and needle in folded_answer


def drop_ungrounded(
    extraction: Extraction,
    *,
    answer: str,
    concern: Concern,
    persona: PersonaDefinition,
) -> Extraction:
    """Remove findings whose quote is not in ``answer`` or whose id is not real.

    A dodge is about what is *absent*, but the text standing in for the missing
    answer is present and must be quoted, because the report prints it.
    """
    folded_answer, _ = fold(answer)
    sub_question_ids = {sq.id for sq in concern.sub_questions}
    red_line_ids = {rl.id for rl in concern.red_lines}
    non_negotiable_ids = {nn.id for nn in persona.non_negotiables}

    red_line_hits = []
    for hit in extraction.red_line_hits:
        if not _is_quoted(hit.span, folded_answer):
            logger.warning("dropped red_line_hit with ungrounded span: %r", hit.span)
            continue
        authored = (
            red_line_ids
            if hit.source_kind is RedLineSourceKind.concern_red_line
            else non_negotiable_ids
        )
        if hit.source_id not in authored:
            logger.warning(
                "dropped red_line_hit citing unknown %s id %r (authored: %s)",
                hit.source_kind.value,
                hit.source_id,
                sorted(authored) or "none",
            )
            continue
        red_line_hits.append(hit)

    claims = []
    for claim in extraction.claims:
        if not _is_quoted(claim.span, folded_answer):
            logger.warning("dropped claim with ungrounded span: %r", claim.span)
            continue
        claims.append(claim)

    coverage = []
    for cov in extraction.sub_question_coverage:
        if cov.id not in sub_question_ids:
            logger.warning("dropped coverage naming unknown sub-question %r", cov.id)
            continue
        if cov.addressed in (Addressed.full, Addressed.partial) and not _is_quoted(
            cov.span, folded_answer
        ):
            logger.warning(
                "dropped %s coverage for %s with ungrounded span: %r",
                cov.addressed.value,
                cov.id,
                cov.span,
            )
            continue
        coverage.append(cov)

    dodges = []
    for dodge in extraction.dodges:
        if dodge.sub_question_id not in sub_question_ids:
            logger.warning(
                "dropped dodge naming unknown sub-question %r", dodge.sub_question_id
            )
            continue
        if not _is_quoted(dodge.answer_span, folded_answer):
            logger.warning(
                "dropped dodge with ungrounded answer_span: %r", dodge.answer_span
            )
            continue
        dodges.append(dodge)

    unchanged = (
        len(red_line_hits) == len(extraction.red_line_hits)
        and len(claims) == len(extraction.claims)
        and len(coverage) == len(extraction.sub_question_coverage)
        and len(dodges) == len(extraction.dodges)
    )
    if unchanged:
        return extraction

    return extraction.model_copy(
        update={
            "red_line_hits": red_line_hits,
            "claims": claims,
            "sub_question_coverage": coverage,
            "dodges": dodges,
        }
    )
