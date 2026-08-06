"""Enforce each sub-question's authored evidence contract, in code.

``SubQuestion.requires`` (``fact`` | ``commitment`` | ``fact_or_commitment``)
reached the extraction prompt and stopped there, so nothing downstream checked
it. A rhetorical span the model happened to label ``partial`` earned the same
``approach_cited`` credit as a documented one. This module closes that: a
coverage row keeps the degree the model gave it only when a surviving claim of
the required type is linked to it and no document refutes that claim. Otherwise
the row is demoted to ``none``, and ``none`` earns nothing anywhere downstream.

Pure code, no model call, no I/O. It rewrites exactly one field,
``SubQuestionCoverage.addressed``, only ever downward, and never adds or removes
a row.

Runs after ``grounding.drop_ungrounded``, which has already discarded ungrounded
claims and trimmed ``evidence_claim_spans`` to links naming a claim that
survived. Every link read here therefore points at text quoted from the answer.

Demotion is binary on the evidence type, not graded. ``full`` and ``partial``
both survive intact once the contract is met: how completely a sub-question was
answered is still the model's judgment. What code owns is whether there is any
verified evidence of the required kind behind the judgment.

Called once, from ``run_extraction``, before scoring and before the extraction is
persisted. That single choke point is why ``score_turn``, the orchestrator's
follow-up decision, and the report all read enforced coverage without knowing
this module exists.
"""

from __future__ import annotations

import logging

from app.pipeline.span_anchor import fold
from app.schemas.content import Concern, Requires
from app.schemas.extraction import Addressed, Claim, ClaimType, Extraction, Verdict

logger = logging.getLogger(__name__)

# Which claim types satisfy which authored requirement. `rhetorical` and
# `value_opinion` satisfy nothing: those are precisely the spans the old engine
# paid `approach_cited` for.
_SATISFYING_TYPES: dict[Requires, frozenset[ClaimType]] = {
    Requires.fact: frozenset({ClaimType.empirical_checkable}),
    Requires.commitment: frozenset({ClaimType.commitment}),
    Requires.fact_or_commitment: frozenset(
        {ClaimType.empirical_checkable, ClaimType.commitment}
    ),
}


def _overlaps(a: str, b: str) -> bool:
    """True when two folded spans quote overlapping text, either way round."""
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def _refuted_spans(extraction: Extraction) -> list[str]:
    """Folded answer spans a surviving document refutation lands on.

    Tier 0 is excluded for the same reason ``score_turn`` excludes it from
    ``false_fact``: a Tier-0 conflict is the presenter disagreeing with their own
    earlier answer, which the ``contradiction`` row charges. It is not a document
    proving the claim false, so it does not disqualify the claim as evidence.
    """
    return [
        fold(fc.answer_span)[0]
        for fc in extraction.fact_checks
        if fc.verdict is Verdict.refuted and fc.tier >= 1
    ]


def _qualifies(claim: Claim, wanted: frozenset[ClaimType], refuted: list[str]) -> bool:
    """True when ``claim`` is of a required type and no document refutes it."""
    if claim.type not in wanted:
        return False
    folded, _ = fold(claim.span)
    return not any(_overlaps(folded, span) for span in refuted)


def enforce_requires(extraction: Extraction, concern: Concern) -> Extraction:
    """Demote every coverage row whose authored evidence contract is unmet."""
    requires_by_id = {sq.id: sq.requires for sq in concern.sub_questions}
    refuted = _refuted_spans(extraction)
    folded_claims = [(fold(c.span)[0], c) for c in extraction.claims]

    def satisfied(cov_links: list[str], wanted: frozenset[ClaimType]) -> bool:
        for link in cov_links:
            folded_link, _ = fold(link)
            for folded_span, claim in folded_claims:
                if not _overlaps(folded_link, folded_span):
                    continue
                if _qualifies(claim, wanted, refuted):
                    return True
        return False

    rows = []
    demoted = False
    for cov in extraction.sub_question_coverage:
        requires = requires_by_id.get(cov.id)
        wanted = _SATISFYING_TYPES.get(requires) if requires is not None else None
        # An id the concern does not author is already dropped by grounding; if
        # one reaches here, pass it through rather than inventing a verdict.
        if cov.addressed is Addressed.none or wanted is None:
            rows.append(cov)
            continue
        if satisfied(cov.evidence_claim_spans, wanted):
            rows.append(cov)
            continue
        assert requires is not None  # guaranteed by wanted is not None
        logger.info(
            "demoted %s coverage on %s to none: no unrefuted %s claim is linked",
            cov.addressed.value,
            cov.id,
            requires.value,
        )
        rows.append(cov.model_copy(update={"addressed": Addressed.none}))
        demoted = True

    if not demoted:
        return extraction
    return extraction.model_copy(update={"sub_question_coverage": rows})
