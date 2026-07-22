"""Reaction service (task 9).

Builds the per-turn persona reply and runs it through the Bedrock client. The
prompt is rebuilt fresh every turn from the authored persona (anti-drift
guardrail #1) and is handed the already-computed ``support_delta`` and
``matched_rows``. The model describes the number; it never sets it. Because the
score is locked before this stage runs, the reply cannot influence scoring.

``run_reaction`` forces the ``PersonaReaction`` schema through tool-use, so the
reply comes back validated (``in_character_reply`` + ``rationale``) rather than
as free text that would need parsing.
"""

from __future__ import annotations

from app.bedrock.client import BedrockClient
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Extraction
from app.schemas.reaction import PersonaReaction
from app.schemas.scoring import ScoreOutput

TOOL_NAME = "emit_reaction"


def _render_persona(persona: PersonaDefinition) -> str:
    return "\n".join(
        [
            f"You are {persona.display_name} ({persona.id}), a federal orals evaluator.",
            f"Voice: {persona.voice}",
            f"Values: {', '.join(persona.values)}",
            f"Wants: {', '.join(persona.wants)}",
            f"Priorities: {', '.join(persona.priorities)}",
        ]
    )


def _render_score(score: ScoreOutput) -> str:
    lines = [
        "The turn has already been scored by code. You cannot change it.",
        f"Support delta this turn: {score.support_delta:+d}",
        f"Matched rubric rows: {', '.join(score.matched_rows) or '(none)'}",
    ]
    if score.capped:
        lines.append(
            "A red line was crossed: this persona's support is now capped for the "
            "rest of the session. React as an evaluator whose confidence just hit a "
            "hard cap."
        )
    return "\n".join(lines)


def build_reaction_prompt(
    *,
    persona: PersonaDefinition,
    concern: Concern,
    extraction: Extraction,
    score: ScoreOutput,
) -> str:
    """Assemble the reaction prompt, rehydrating the persona fresh and stating the
    locked score.

    The reply must reflect the number that code already produced. It describes
    the score; nothing here lets the model set or move it.
    """
    return "\n\n".join(
        [
            "You are the reaction stage of an oral-defense rehearsal. Reply in "
            f"character using the {TOOL_NAME} tool. Your reply must be consistent "
            "with the score below, which was computed by code before you ran. You "
            "never assign or change the score.",
            "## Evaluator persona",
            _render_persona(persona),
            "## Concern under discussion",
            f"{concern.concern_id}: {concern.core_ask}",
            "## Locked score for the presenter's latest answer",
            _render_score(score),
            "## What the extraction found in the answer",
            extraction.model_dump_json(indent=2),
            "## Your task",
            "Respond in this evaluator's voice, reacting to the answer in a way that "
            "matches the locked score, then give a one-line rationale tying your "
            "reaction to the matched rubric rows.",
            "Write the reply and the rationale the way a real evaluator speaks: "
            "plain and direct. Use short sentences. Do not use em dashes. Do not "
            "pad either one with three-part lists or promotional adjectives.",
        ]
    )


def run_reaction(
    *,
    persona: PersonaDefinition,
    concern: Concern,
    extraction: Extraction,
    score: ScoreOutput,
    client: BedrockClient,
) -> PersonaReaction:
    """Build the prompt and force the ``PersonaReaction`` schema through the tool."""
    prompt = build_reaction_prompt(
        persona=persona,
        concern=concern,
        extraction=extraction,
        score=score,
    )
    return client.extract(prompt, content_schema=PersonaReaction, tool_name=TOOL_NAME)
