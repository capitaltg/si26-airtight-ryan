"""Discard model findings the answer does not support, before the scorer sees them.

``Claim.span``, ``RedLineHit.span`` and ``SubQuestionCoverage.span`` are all
documented as verbatim quotes from the answer, and ``Claim.span`` says outright
that a claim without one does not count. Nothing enforced that. A fabricated
span on a red-line hit bills -2 and pins the persona's meter at the cap,
stickily and forever, on the model's word alone.

Pure code, no model call, no I/O. It only ever removes: a whole finding, or a
link inside one. It never rewrites the content of a field and never raises.
Runs after ``span_anchor.reanchor_spans`` so a replayed span is mapped onto the
current phrasing before the membership test — reversed, a whitespace-only
retype would discard legitimate findings. ``RedLineHit.source_id`` is also
validated against the authored ids of its ``source_kind``.

A ``FactCheck`` is kept only when its ``answer_span`` is quoted in the answer
and its ``source_quote`` is quoted in the document named by
``source_document_id``. Tier 2 (open web) is never verifiable — there is no
document to check its quote against — so it is always dropped outright, ahead
of and independent from the document lookup that catches a fabricated or
mislabeled ``source_document_id`` on a Tier-1 check.

``SubQuestionCoverage.evidence_claim_spans`` names the claims that carry a
sub-question's answer. A link is kept only when it quotes the span of a claim
that survived this same pass, so a link cannot point at evidence that was just
discarded. ``pipeline.coverage_contract`` reads what is left.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from app.pipeline.span_anchor import fold
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Addressed, Extraction, RedLineSourceKind, SourceDocument

logger = logging.getLogger(__name__)


def _is_quoted(span: str | None, folded_answer: str) -> bool:
    """True when ``span`` occurs in the answer, ignoring case and whitespace runs."""
    if not span:
        return False
    needle, _ = fold(span)
    return bool(needle) and needle in folded_answer


def _links_a_claim(link: str, folded_claim_spans: list[str]) -> bool:
    """True when ``link`` quotes the span of a claim that survived grounding.

    Equal or narrower than a claim span, never broader: a coverage row may cite
    part of a claim, but stretching one short claim across a wider quote would
    let a single grounded phrase carry text it never covered.
    """
    needle, _ = fold(link)
    if not needle:
        return False
    return any(needle == span or needle in span for span in folded_claim_spans)


def drop_ungrounded(
    extraction: Extraction,
    *,
    answer: str,
    concern: Concern,
    persona: PersonaDefinition,
    prior_answers: Mapping[int, str],
    documents: Mapping[SourceDocument, str],
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

    # Folded once, from the claims that SURVIVED: a link naming a claim this pass
    # just discarded is not evidence of anything.
    folded_claim_spans = [fold(claim.span)[0] for claim in claims]

    coverage = []
    links_trimmed = False
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
        kept = [
            link for link in cov.evidence_claim_spans
            if _links_a_claim(link, folded_claim_spans)
        ]
        if len(kept) != len(cov.evidence_claim_spans):
            logger.warning(
                "trimmed %d evidence_claim_span(s) on coverage %s naming no surviving claim",
                len(cov.evidence_claim_spans) - len(kept),
                cov.id,
            )
            cov = cov.model_copy(update={"evidence_claim_spans": kept})
            links_trimmed = True
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

    flags = []
    for flag in extraction.consistency_flags:
        prior = prior_answers.get(flag.conflicts_with_turn)
        if prior is None:
            logger.warning(
                "dropped Tier-0 flag naming turn %s (stored turns: %s)",
                flag.conflicts_with_turn,
                sorted(prior_answers) or "none",
            )
            continue
        if not _is_quoted(flag.current_answer_span, folded_answer):
            logger.warning(
                "dropped Tier-0 flag with ungrounded current_answer_span: %r",
                flag.current_answer_span,
            )
            continue
        folded_prior, _ = fold(prior)
        if not _is_quoted(flag.prior_answer_span, folded_prior):
            logger.warning(
                "dropped Tier-0 flag whose prior_answer_span is absent from turn %s: %r",
                flag.conflicts_with_turn,
                flag.prior_answer_span,
            )
            continue
        flags.append(flag)

    # Folded once per document, not once per check: folding is O(len) and these
    # are the full RFP and proposal.
    folded_documents = {name: fold(text)[0] for name, text in documents.items()}

    fact_checks = []
    for check in extraction.fact_checks:
        if not _is_quoted(check.answer_span, folded_answer):
            logger.warning(
                "dropped fact_check with ungrounded answer_span: %r", check.answer_span
            )
            continue
        if check.tier == 2:
            # Tier 2 is open web: there is no registered document a tier-2 check
            # could name, so it can never be verified, regardless of what
            # source_document_id it happens to carry. Dropped here rather than
            # billed on the model's word.
            logger.warning(
                "dropped tier-2 fact_check (open web is unverifiable): %r", check.claim
            )
            continue
        folded_source = folded_documents.get(check.source_document_id)
        if folded_source is None:
            logger.warning(
                "dropped fact_check citing unregistered document %r",
                check.source_document_id.value,
            )
            continue
        if not _is_quoted(check.source_quote, folded_source):
            logger.warning(
                "dropped fact_check whose source_quote is absent from %s: %r",
                check.source_document_id.value,
                check.source_quote,
            )
            continue
        fact_checks.append(check)

    unchanged = (
        not links_trimmed
        and len(red_line_hits) == len(extraction.red_line_hits)
        and len(claims) == len(extraction.claims)
        and len(coverage) == len(extraction.sub_question_coverage)
        and len(dodges) == len(extraction.dodges)
        and len(flags) == len(extraction.consistency_flags)
        and len(fact_checks) == len(extraction.fact_checks)
    )
    if unchanged:
        return extraction

    return extraction.model_copy(
        update={
            "red_line_hits": red_line_hits,
            "claims": claims,
            "sub_question_coverage": coverage,
            "dodges": dodges,
            "consistency_flags": flags,
            "fact_checks": fact_checks,
        }
    )
