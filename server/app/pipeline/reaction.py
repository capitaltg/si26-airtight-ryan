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

from app.bedrock.cache import CacheKeyInput, normalize_answer
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


def _render_extraction_summary(extraction: Extraction) -> str:
    """A compact view of just what the reply references: claim texts, dodge types,
    and red-line reasons.

    The number is already locked and passed via ``_render_score``, so the reply
    only needs the qualitative shape of the answer — not the full ``Extraction``
    JSON (sub-question coverage, fact checks, per-field scaffolding), which only
    padded the second Bedrock call.

    Consistency flags are the exception to that trimming. ``matched_rows`` tells
    the persona a contradiction was scored but not what it contradicted, and a
    persona told to react to an invisible penalty invents a source for it — in
    one observed run, an "org chart" and a "technical volume" that never existed
    in the session. Passing both the current and prior spans is what keeps the
    reply tied to the presenter's own words. Same reason ``red_line_hits`` passes
    ``why``.
    """
    lines: list[str] = []
    if extraction.claims:
        lines.append("Claims:")
        lines.extend(f"  - {claim.text}" for claim in extraction.claims)
    if extraction.dodges:
        lines.append("Dodges:")
        lines.extend(f"  - {dodge.type.value}" for dodge in extraction.dodges)
    if extraction.consistency_flags:
        # Same predicate `score_turn` and `_turn_findings` use: an openly
        # explained revision is not a contradiction, and the persona must not
        # be told it is one just because both surface from the same list.
        hidden = [f for f in extraction.consistency_flags if not f.acknowledged_revision]
        revised = [f for f in extraction.consistency_flags if f.acknowledged_revision]
        if hidden:
            lines.append("Contradicts an earlier answer:")
            lines.extend(
                f'  - (conflicts with turn {flag.conflicts_with_turn}) now: "'
                f'{flag.current_answer_span}" / earlier: "{flag.prior_answer_span}"'
                for flag in hidden
            )
        if revised:
            lines.append("Openly revised an earlier answer:")
            lines.extend(
                f'  - (revises turn {flag.conflicts_with_turn}) now: "'
                f'{flag.current_answer_span}" / earlier: "{flag.prior_answer_span}"'
                for flag in revised
            )
    if extraction.red_line_hits:
        lines.append("Red lines crossed:")
        lines.extend(f"  - {hit.why}" for hit in extraction.red_line_hits)
    return "\n".join(lines) if lines else "(nothing notable extracted from the answer)"


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
    if score.integrity_ceiling:
        # Named for the same reason consistency spans are passed above: a persona
        # told to react to an invisible adjustment invents a source for it.
        # `support_delta` is rendered without a sign here, unlike the line above:
        # a ceilinged turn is always 0 or below and "+0" reads as a gain.
        withheld = score.raw_support_delta - score.support_delta
        lines.append(
            f"Something in this answer was not true, so the turn is held at "
            f"{score.support_delta}: {withheld:+d} of credit the answer otherwise "
            "earned was withheld. React to an answer that covered ground but got "
            "something wrong."
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
            _render_extraction_summary(extraction),
            "## Your task",
            "Respond in this evaluator's voice, reacting to the answer in a way that "
            "matches the locked score, then give a one-line rationale tying your "
            "reaction to the matched rubric rows.",
            "Write the reply and the rationale the way a real evaluator speaks: "
            "plain and direct. Use short sentences. Do not use em dashes. Do not "
            "pad either one with three-part lists or promotional adjectives.",
        ]
    )


def build_clarification_prompt(
    *,
    persona: PersonaDefinition,
    concern: Concern,
    question: str,
) -> str:
    """Assemble the score-free clarification prompt.

    Deliberately omits ``_render_score`` and ``_render_extraction_summary``:
    there is no score and nothing was extracted. The evaluator answers the
    presenter's clarifying question in character without evaluating, scoring, or
    judging the presenter — the presenter still owes a real answer afterward.
    """
    return "\n\n".join(
        [
            "You are an evaluator in an oral-defense rehearsal. The presenter has "
            "asked you a clarifying question about what you are looking for. Answer "
            "it briefly and in character. This is NOT a scored answer: you are not "
            "evaluating, scoring, or judging the presenter, and asking is not a "
            "dodge. Do not assign or mention any score.",
            "## Evaluator persona",
            _render_persona(persona),
            "## Concern under discussion",
            f"{concern.concern_id}: {concern.core_ask}",
            "## The presenter's clarifying question",
            question,
            "## Your task",
            "Answer the clarifying question in this evaluator's voice: say what you "
            "are actually looking for on this concern, briefly. Then make clear you "
            "still expect a real answer to the original ask. Write the way a real "
            "evaluator speaks: plain and direct, short sentences. Do not use em "
            "dashes. Do not pad with three-part lists or promotional adjectives.",
        ]
    )


def run_clarification(
    *,
    persona: PersonaDefinition,
    concern: Concern,
    question: str,
    client: BedrockClient,
) -> str:
    """Plain-text clarification reply. No tool-use, no ``PersonaReaction``, no
    scoring artifacts — just the ``react`` path, so nothing here can move a
    number.

    The question is presenter-typed text like an answer, so it gets the same
    normalized-cache-key treatment: the model sees the raw question, but a
    whitespace- or case-only variant of one question replays the same reply.
    """
    normalized = normalize_answer(question)
    return client.react(
        build_clarification_prompt(persona=persona, concern=concern, question=question),
        cache_key=CacheKeyInput(
            content=build_clarification_prompt(
                persona=persona, concern=concern, question=normalized
            ),
            normalized_answer=normalized,
        ),
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
