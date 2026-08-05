"""Extraction service (task 7, step 5).

Builds the per-turn extraction prompt and runs it through the Bedrock client.
The prompt is rebuilt fresh every turn from the authored content
(anti-drift guardrail #1): persona, RFP, proposal, the active concern, and the
running claim ledger with verbatim spans so Tier-0 (in-session) contradictions
can be detected. The model classifies into the ``Extraction`` schema; it never
sees or sets the score.

``run_extraction`` returns an ``ExtractionResult`` bundling the validated
``Extraction`` with the code-computed ``Conciseness``. Conciseness is deliberately
kept off the ``Extraction`` tool schema (see ``schemas.extraction``), so it is
attached here rather than emitted by the model.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.bedrock.cache import CacheKeyInput, normalize_answer
from app.bedrock.client import BedrockClient
from app.config import settings
from app.content.loader import Content
from app.db.models import ClaimLedger
from app.pipeline.conciseness import compute_conciseness
from app.pipeline.extraction_pin import ExtractionPin, NullExtractionPin, extraction_key
from app.pipeline.grounding import drop_ungrounded
from app.pipeline.span_anchor import reanchor_spans
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Conciseness, Extraction

logger = logging.getLogger(__name__)

TOOL_NAME = "record_extraction"


@dataclass(frozen=True)
class ExtractionResult:
    """What the pipeline hands to the scorer: the validated extraction plus the
    code-owned conciseness signals."""

    extraction: Extraction
    conciseness: Conciseness


def _render_persona(persona: PersonaDefinition) -> str:
    non_negotiables = "; ".join(f"[{nn.id}] {nn.text}" for nn in persona.non_negotiables)
    return "\n".join(
        [
            f"You are {persona.display_name} ({persona.id}).",
            f"Voice: {persona.voice}",
            f"Demographics: {persona.demographics}",
            f"Values: {', '.join(persona.values)}",
            f"Wants: {', '.join(persona.wants)}",
            f"Priorities: {', '.join(persona.priorities)}",
            f"Non-negotiables: {non_negotiables}",
        ]
    )


def _render_concern(concern: Concern) -> str:
    sub = "\n".join(
        f"  - [{sq.id}] {sq.text} (requires: {sq.requires.value})"
        for sq in concern.sub_questions
    )
    red = "\n".join(f"  - [{line.id}] {line.text}" for line in concern.red_lines)
    return "\n".join(
        [
            f"Concern: {concern.concern_id}",
            f"Core ask: {concern.core_ask}",
            "Sub-questions:",
            sub,
            "Red lines (crossing any is a hard cap):",
            red,
            f"What would satisfy: {concern.what_would_satisfy}",
        ]
    )


# Spelled out because the model was filing Tier-1 document conflicts under
# consistency_flags, which double-scores one error (-1 false_fact, -1
# contradiction) and blames the presenter for contradicting themselves when they
# did not. The empty-ledger case is stated as its own sentence because the model
# raised a flag against turn 0 on the session's first turn.
_LEDGER_RULES = (
    "Rules for `consistency_flags`. A flag means the answer conflicts with "
    "something the PRESENTER said in an earlier turn, listed above. "
    "`conflicts_with_turn` must be one of the turn numbers in that list. "
    "If the ledger says there are no prior claims, `consistency_flags` must be "
    "empty — there is nothing yet to contradict. "
    "A conflict with the solicitation or the written proposal is NOT a "
    "consistency flag: record it in `fact_checks` with `tier: 1` and a "
    "`refuted` verdict. Never record the same conflict in both fields."
)


def _render_ledger(prior_claims: Sequence[ClaimLedger]) -> str:
    if not prior_claims:
        return "(no prior claims: this is the first scored answer of the session)"
    return "\n".join(
        f"  - [turn {row.turn_index}] \"{row.span}\": {row.text}" for row in prior_claims
    )


def build_extraction_static_prefix(
    *,
    persona: PersonaDefinition,
    content: Content,
) -> str:
    """The turn-invariant head of the extraction prompt: the system instructions,
    the persona block, the RFP, and the proposal.

    This prefix is byte-identical across every turn of a given persona's session,
    so it carries the Bedrock prompt-cache breakpoint. It clears Sonnet 4.5's
    1024-token minimum cacheable prefix on the RFP + proposal alone.
    """
    return "\n\n".join(
        [
            "You are the extraction stage of an oral-defense rehearsal scorer. "
            "Classify the presenter's answer against the schema using the "
            f"{TOOL_NAME} tool. Quote spans verbatim from the answer; a claim with "
            "no verbatim span does not count. You never assign a score.",
            "When you write a free-text reason in the schema (for example the "
            "'why' behind a red-line hit), write it the way a person would: plain "
            "and direct, short sentences, no em dashes, no three-part lists, no "
            "promotional adjectives.",
            "## Evaluator persona (context for what this evaluator cares about)",
            _render_persona(persona),
            "## Solicitation (RFP / PWS)",
            content.rfp_text,
            "## Written proposal",
            content.proposal_text,
        ]
    )


def build_extraction_dynamic_suffix(
    *,
    answer: str,
    concern: Concern,
    prior_claims: Sequence[ClaimLedger],
) -> str:
    """The turn-varying tail: the active concern, the running claim ledger, and
    the answer under evaluation.

    This is the anti-drift rebuild — it is sent fresh, uncached, every turn.
    Prior claim spans are included exactly as stored so the model can flag a
    Tier-0 contradiction against something the presenter already committed to.
    """
    return "\n\n".join(
        [
            "## Active concern",
            _render_concern(concern),
            "## Prior claim ledger (verbatim spans; flag Tier-0 contradictions "
            "against these)",
            _render_ledger(prior_claims),
            _LEDGER_RULES,
            "## Presenter's answer to classify",
            answer,
        ]
    )


def drop_unanchored_flags(
    extraction: Extraction, prior_claims: Sequence[ClaimLedger]
) -> Extraction:
    """Remove Tier-0 flags that do not name a turn in the claim ledger.

    A ``ConsistencyFlag`` is a conflict with something the presenter already
    said, so ``conflicts_with_turn`` has to be a turn that is actually in the
    ledger. The model has been observed filing document conflicts here (that is
    Tier-1, and scores as ``false_fact``) and raising a flag on the session's
    first turn, where the ledger is empty and ``conflicts_with_turn: 0`` points
    at the turn being scored. Either way the presenter loses a point the rubric
    never authorized, so the flag is dropped before it reaches the scorer.

    The prompt states the rule; this is the code that does not depend on the
    model following it. Only ``consistency_flags`` is touched — a real Tier-1
    conflict still scores through ``fact_checks``.
    """
    if not extraction.consistency_flags:
        return extraction

    ledger_turns = {row.turn_index for row in prior_claims}
    kept = [f for f in extraction.consistency_flags if f.conflicts_with_turn in ledger_turns]
    if len(kept) == len(extraction.consistency_flags):
        return extraction

    for flag in extraction.consistency_flags:
        if flag.conflicts_with_turn not in ledger_turns:
            logger.warning(
                "dropped Tier-0 flag naming turn %s (ledger turns: %s): %s",
                flag.conflicts_with_turn,
                sorted(ledger_turns) or "none",
                flag.detail,
            )
    return extraction.model_copy(update={"consistency_flags": kept})


def build_extraction_prompt(
    *,
    answer: str,
    concern: Concern,
    persona: PersonaDefinition,
    content: Content,
    prior_claims: Sequence[ClaimLedger],
) -> str:
    """Assemble the full extraction prompt (prefix + suffix) as one string.

    Kept as the single source of the assembled text; the reassembly here is
    byte-identical to the two blocks ``run_extraction`` sends to Bedrock.
    """
    return "\n\n".join(
        [
            build_extraction_static_prefix(persona=persona, content=content),
            build_extraction_dynamic_suffix(
                answer=answer, concern=concern, prior_claims=prior_claims
            ),
        ]
    )


def _blocks(
    *,
    persona: PersonaDefinition,
    content: Content,
    answer: str,
    concern: Concern,
    prior_claims: Sequence[ClaimLedger],
) -> list[dict[str, Any]]:
    """The two content blocks sent to Bedrock: a cached static prefix (persona +
    RFP + proposal) and an uncached dynamic suffix (concern + ledger + answer).

    Factored out so the sent blocks and the hashed blocks (built from the
    normalized answer) cannot drift apart — both go through this one helper.
    """
    return [
        {
            "type": "text",
            "text": build_extraction_static_prefix(persona=persona, content=content),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": build_extraction_dynamic_suffix(
                answer=answer, concern=concern, prior_claims=prior_claims
            ),
        },
    ]


def run_extraction(
    *,
    answer: str,
    concern: Concern,
    persona: PersonaDefinition,
    content: Content,
    prior_claims: Sequence[ClaimLedger],
    client: BedrockClient,
    pin: ExtractionPin | None = None,
) -> ExtractionResult:
    """Build the prompt, force the ``Extraction`` schema through the tool, and
    attach code-computed conciseness.

    The prompt goes out as two content blocks: a cached static prefix (persona +
    RFP + proposal) and an uncached dynamic suffix (concern + ledger + answer).

    ``pin`` makes the score a function of the input. The first extraction for a
    given (normalized answer, persona, concern, ledger, content fingerprint) is
    stored and replayed forever after, so the model cannot disagree with itself
    across runs. It defaults to :class:`NullExtractionPin`, which keeps direct
    callers — the golden suite above all — fully live.

    Post-processing runs on the replay path too, and the order matters. A pinned
    span was quoted out of an earlier phrasing, so ``reanchor_spans`` maps it onto
    this answer first; then ``drop_ungrounded`` discards anything the answer does
    not actually support; then ``drop_unanchored_flags`` handles Tier-0. Running
    grounding before anchoring would throw out real findings whenever a presenter
    retypes the same answer with different spacing.
    """
    resolved_pin: ExtractionPin = pin if pin is not None else NullExtractionPin()
    key = extraction_key(
        answer=answer,
        persona_id=persona.id,
        concern_id=concern.concern_id,
        prior_claims=prior_claims,
        extraction_fingerprint=content.extraction_fingerprint,
    )

    pinned = resolved_pin.get(key)
    if pinned is not None:
        extraction = Extraction.model_validate(pinned)
    else:
        content_blocks = _blocks(
            persona=persona,
            content=content,
            answer=answer,
            concern=concern,
            prior_claims=prior_claims,
        )
        normalized = normalize_answer(answer)
        extraction = client.extract(
            content_blocks,
            content_schema=Extraction,
            tool_name=TOOL_NAME,
            cache_key=CacheKeyInput(
                content=_blocks(
                    persona=persona,
                    content=content,
                    answer=normalized,
                    concern=concern,
                    prior_claims=prior_claims,
                ),
                normalized_answer=normalized,
            ),
        )
        resolved_pin.put(
            key,
            tool_input=extraction.model_dump(mode="json"),
            model_id=settings.bedrock_model_id,
        )
        canonical = resolved_pin.get(key)
        if canonical is not None:
            extraction = Extraction.model_validate(canonical)

    anchored = reanchor_spans(extraction, answer)
    grounded = drop_ungrounded(
        anchored, answer=answer, concern=concern, persona=persona
    )
    guarded = drop_unanchored_flags(grounded, prior_claims)
    conciseness = compute_conciseness(answer, guarded)
    return ExtractionResult(extraction=guarded, conciseness=conciseness)
