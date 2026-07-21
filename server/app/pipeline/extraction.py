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

from collections.abc import Sequence
from dataclasses import dataclass

from app.bedrock.client import BedrockClient
from app.content.loader import Content
from app.db.models import ClaimLedger
from app.pipeline.conciseness import compute_conciseness
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Conciseness, Extraction

TOOL_NAME = "record_extraction"


@dataclass(frozen=True)
class ExtractionResult:
    """What the pipeline hands to the scorer: the validated extraction plus the
    code-owned conciseness signals."""

    extraction: Extraction
    conciseness: Conciseness


def _render_persona(persona: PersonaDefinition) -> str:
    return "\n".join(
        [
            f"You are {persona.display_name} ({persona.id}).",
            f"Voice: {persona.voice}",
            f"Demographics: {persona.demographics}",
            f"Values: {', '.join(persona.values)}",
            f"Wants: {', '.join(persona.wants)}",
            f"Priorities: {', '.join(persona.priorities)}",
            f"Non-negotiables: {', '.join(persona.non_negotiables)}",
        ]
    )


def _render_concern(concern: Concern) -> str:
    sub = "\n".join(
        f"  - [{sq.id}] {sq.text} (requires: {sq.requires.value})"
        for sq in concern.sub_questions
    )
    red = "\n".join(f"  - {line}" for line in concern.red_lines)
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


def _render_ledger(prior_claims: Sequence[ClaimLedger]) -> str:
    if not prior_claims:
        return "(no prior claims: this is the first scored answer of the session)"
    return "\n".join(
        f"  - [turn {row.turn_index}] \"{row.span}\": {row.text}" for row in prior_claims
    )


def build_extraction_prompt(
    *,
    answer: str,
    concern: Concern,
    persona: PersonaDefinition,
    content: Content,
    prior_claims: Sequence[ClaimLedger],
) -> str:
    """Assemble the extraction prompt, rehydrating all authored context verbatim.

    Prior claim spans are included exactly as stored so the model can flag a
    Tier-0 contradiction against something the presenter already committed to.
    """
    return "\n\n".join(
        [
            "You are the extraction stage of an oral-defense rehearsal scorer. "
            "Classify the presenter's answer against the schema using the "
            f"{TOOL_NAME} tool. Quote spans verbatim from the answer; a claim with "
            "no verbatim span does not count. You never assign a score.",
            "## Evaluator persona (context for what this evaluator cares about)",
            _render_persona(persona),
            "## Solicitation (RFP / PWS)",
            content.rfp_text,
            "## Written proposal",
            content.proposal_text,
            "## Active concern",
            _render_concern(concern),
            "## Prior claim ledger (verbatim spans; flag Tier-0 contradictions "
            "against these)",
            _render_ledger(prior_claims),
            "## Presenter's answer to classify",
            answer,
        ]
    )


def run_extraction(
    *,
    answer: str,
    concern: Concern,
    persona: PersonaDefinition,
    content: Content,
    prior_claims: Sequence[ClaimLedger],
    client: BedrockClient,
) -> ExtractionResult:
    """Build the prompt, force the ``Extraction`` schema through the tool, and
    attach code-computed conciseness."""
    prompt = build_extraction_prompt(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=prior_claims,
    )
    extraction = client.extract(prompt, content_schema=Extraction, tool_name=TOOL_NAME)
    conciseness = compute_conciseness(answer, extraction)
    return ExtractionResult(extraction=extraction, conciseness=conciseness)
