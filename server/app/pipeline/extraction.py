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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.bedrock.cache import CacheKeyInput, normalize_answer
from app.bedrock.client import BedrockClient
from app.config import settings
from app.content.loader import Content
from app.db.models import ClaimLedger
from app.pipeline.conciseness import compute_conciseness
from app.pipeline.coverage_contract import enforce_requires
from app.pipeline.extraction_pin import ExtractionPin, NullExtractionPin, extraction_key
from app.pipeline.grounding import drop_ungrounded
from app.pipeline.span_anchor import reanchor_spans
from app.schemas.content import Concern, PersonaDefinition
from app.schemas.extraction import Conciseness, Extraction, SourceDocument

logger = logging.getLogger(__name__)

TOOL_NAME = "record_extraction"

# Identity of the extraction contract: the prompt's semantics plus the tool it
# forces. Hashed into `extraction_key`, so bumping it is how a prompt fix reaches
# inputs that are already pinned.
#
# Bump when the prompt changes what the model is asked to report: new or removed
# instructions that change classification behavior, content newly rendered into
# the prompt (persona exemplars, for one), a different tool name, a change in
# extraction policy.
#
# Do not bump for comments, formatting, or a reword that leaves the ask
# identical — the pin exists so that churn does not cost a model call.
#
# 2: the coverage and fact-check rules were added to the prompt and
# `SubQuestionCoverage.evidence_claim_spans` was added to the tool schema. A
# pinned v1 extraction has no links at all, so replaying it would demote every
# coverage row to `none`. The bump makes those pins miss on purpose.
#
# v3: `acknowledged_revision` became score-bearing (rubric v4) and the prompt now
# states the three-part bar for it. A pinned v2 extraction set that field with no
# rules at all, so replaying one would feed unrated judgment straight into the
# number. The bump makes those pins miss on purpose.
#
# v4: the prompt now asks for `SubQuestionCoverage.span`. It never had, so the
# model left it null and `grounding.drop_ungrounded` discarded every full/partial
# row it saw -- real coverage thrown away, and `approach_cited` lost with it. A
# pinned v3 extraction carries those nulls, so replaying one would keep throwing
# the same rows away. The bump makes those pins miss on purpose.
#
# v5: the persona's hand-graded exemplars are rendered into the prefix. They were
# authored, stored, and editable, but reached no prompt, so the calibration
# remedy this suite documents ("add a worked exemplar") changed nothing. New
# content in the prompt changes classification behavior, which is exactly what
# this constant gates, so v4 pins miss on purpose.
EXTRACTOR_CONTRACT_VERSION = 5

ExtractionSource = Literal["pin", "response_cache", "fresh"]


@dataclass(frozen=True)
class ExtractionProvenance:
    """How this turn's extraction was produced, recorded on the turn row.

    Nothing reads it yet — no report field, no API field, no UI. It exists so
    "did this turn call the model, and under which contract" has an answer in the
    database instead of in a log that has rotated away.
    """

    source: ExtractionSource
    key: str
    contract_version: int
    model_id: str


@dataclass(frozen=True)
class ExtractionResult:
    """What the pipeline hands to the scorer: the validated extraction plus the
    code-owned conciseness signals and how the extraction was produced."""

    extraction: Extraction
    conciseness: Conciseness
    provenance: ExtractionProvenance


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


def _render_exemplars(persona: PersonaDefinition) -> str | None:
    """The persona's hand-graded worked examples, as classification guidance.

    ``Exemplar.support_delta`` is deliberately left out. The extraction stage is
    told it never assigns a score, and ``scoring.score_turn`` owns the number in
    pure code; handing the model a column of graded deltas invites it to reason
    toward one. What extraction needs from an exemplar is the judgment in
    ``note`` — what counts as a dodge for this evaluator, what counts as bare
    reassurance — and that survives without the figure.

    Returns ``None`` for a persona with no exemplars, so an unauthored persona
    contributes no empty heading to the cached prefix.
    """
    if not persona.exemplars:
        return None
    entries = "\n".join(
        f'  - Answer: "{ex.user.strip()}"\n    How it was judged: {ex.note.strip()}'
        for ex in persona.exemplars
    )
    return "\n".join(
        [
            "## Worked examples (how answers of this shape were graded by hand "
            "for this evaluator)",
            "Read them for classification only: what counts as a dodge here, what "
            "counts as generic reassurance, what counts as backed evidence. They "
            "carry no score and you still never assign one.",
            entries,
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
            "Sub-questions (the `requires` tag names the kind of claim that "
            "counts; see the coverage rules above):",
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
# raised a flag against turn 0 on the session's first turn. The revision bar is
# spelled out because `acknowledged_revision` became score-bearing in rubric v4:
# an undefined field feeding the number is model whim feeding the number.
_LEDGER_RULES = (
    "Rules for `consistency_flags`. A flag means the answer conflicts with "
    "something the PRESENTER said in an earlier turn, listed above. "
    "`conflicts_with_turn` must be one of the turn numbers in that list. "
    "If the ledger says there are no prior claims, `consistency_flags` must be "
    "empty — there is nothing yet to contradict. "
    "A conflict with the solicitation or the written proposal is NOT a "
    "consistency flag: record it in `fact_checks` with `tier: 1` and a "
    "`refuted` verdict. Never record the same conflict in both fields. "
    "Rules for `acknowledged_revision`. Set it true only when the answer does "
    "all three of these: refers to the earlier position, states the new "
    "position, and gives a reason for the change. If any one of the three is "
    "missing, set it false. Naming the old and the new position without a "
    "reason is not an acknowledged revision. "
    'TRUE: "Earlier I said a single weekend; after the dry run we found the '
    'index rebuild runs long, so we are going region by region." '
    'FALSE: "Earlier I would have pointed to data migration, but our top risk '
    'is staffing ramp-up."'
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

    The persona's worked exemplars ride here rather than in the per-turn suffix:
    they are turn-invariant, so putting them in the cached half is what keeps the
    calibration lever free to grow without a per-turn token cost.
    """
    exemplars = _render_exemplars(persona)
    return "\n\n".join(
        block
        for block in [
            "You are the extraction stage of an oral-defense rehearsal scorer. "
            "Classify the presenter's answer against the schema using the "
            f"{TOOL_NAME} tool. Quote spans verbatim from the answer; a claim with "
            "no verbatim span does not count. You never assign a score.",
            "Evidence rules. Every span you emit must be copied character for "
            "character out of the text it quotes. `answer_span` and "
            "`current_answer_span` come from the presenter's answer below. "
            "`prior_answer_span` comes from the earlier turn you name in "
            "`conflicts_with_turn`: in the claim ledger, each line is `[turn N] "
            "\"<quoted span>\": <your own earlier restatement>`. Copy "
            "`prior_answer_span` from the quoted span inside the quotation marks "
            "only, never from the restatement after the colon, since that text is "
            "your own paraphrase and will not be found in the presenter's actual "
            "answer. `source_quote` "
            "comes from the document you name in `source_document_id`: `rfp_pws` "
            "is the solicitation above, `written_proposal` is the proposal above. "
            "`red_line_hits.source_id` must be one of the bracketed ids listed "
            "with the red lines and non-negotiables. A finding whose evidence "
            "cannot be found in its stated source is discarded before scoring, "
            "so an unverifiable finding is worth nothing.",
            "Coverage rules. Each sub-question in the active concern carries a "
            "`requires` tag. `fact` means an `empirical_checkable` claim, "
            "`commitment` means a `commitment` claim, and `fact_or_commitment` "
            "means either one. When you mark a sub-question `full` or `partial`, "
            "put the verbatim quote from the answer in `span`. A row with no "
            "span is discarded, exactly like a claim with no span. Then "
            "put in `evidence_claim_spans` the span of every claim in `claims` "
            "that carries that answer, copied character for character from the "
            "claim's own `span`. Do not link a claim you did not also emit in "
            "`claims`. A coverage row with no linked claim of the required type "
            "is scored as not addressed, so restating the question or answering "
            "it with enthusiasm earns nothing.",
            "Fact-check rules. Record a `fact_check` when the solicitation or the "
            "written proposal CONFIRMS a checkable claim, not only when one is "
            "refuted. Use `tier: 1`, `verdict: supported`, and the confirming "
            "`source_quote`. A confirmed checkable claim is real evidence and "
            "the scorer credits it, so leaving it out costs the presenter.",
            "When you write a free-text reason in the schema (for example the "
            "'why' behind a red-line hit), write it the way a person would: plain "
            "and direct, short sentences, no em dashes, no three-part lists, no "
            "promotional adjectives.",
            "## Evaluator persona (context for what this evaluator cares about)",
            _render_persona(persona),
            exemplars,
            "## Solicitation (RFP / PWS)",
            content.rfp_text,
            "## Written proposal",
            content.proposal_text,
        ]
        if block is not None
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
    prior_answers: Mapping[int, str],
    client: BedrockClient,
    pin: ExtractionPin | None = None,
) -> ExtractionResult:
    """Build the prompt, force the ``Extraction`` schema through the tool, and
    attach code-computed conciseness.

    The prompt goes out as two content blocks: a cached static prefix (persona +
    RFP + proposal) and an uncached dynamic suffix (concern + ledger + answer).

    ``pin`` makes the score a function of the input *and* of the contract that
    produced it. The first extraction for a given (normalized answer, persona,
    concern, ledger, prior answers, content fingerprint, contract version, model
    id) is stored and replayed forever after, so the model cannot disagree with
    itself across runs — while a model upgrade or an ``EXTRACTOR_CONTRACT_VERSION``
    bump misses on purpose. It defaults to :class:`NullExtractionPin`, which keeps
    direct callers — the golden suite above all — fully live.

    Post-processing runs on the replay path too, and the order matters. A pinned
    span was quoted out of an earlier phrasing, so ``reanchor_spans`` maps it onto
    this answer first; then ``drop_ungrounded`` discards anything the answer does
    not actually support, Tier-0 contradictions included; then ``enforce_requires``
    demotes any sub-question whose authored ``requires`` type has no surviving claim
    behind it. Running grounding before anchoring would throw out real findings
    whenever a presenter retypes the same answer with different spacing, and running
    the contract check before grounding would let a discarded claim satisfy a
    sub-question.
    """
    model_id = settings.bedrock_model_id
    resolved_pin: ExtractionPin = pin if pin is not None else NullExtractionPin()
    key = extraction_key(
        answer=answer,
        persona_id=persona.id,
        concern_id=concern.concern_id,
        prior_claims=prior_claims,
        prior_answers=prior_answers,
        extraction_fingerprint=content.extraction_fingerprint,
        extractor_contract_version=EXTRACTOR_CONTRACT_VERSION,
        model_id=model_id,
    )

    pinned = resolved_pin.get(key)
    source: ExtractionSource
    if pinned is not None:
        extraction = Extraction.model_validate(pinned)
        source = "pin"
    else:
        content_blocks = _blocks(
            persona=persona,
            content=content,
            answer=answer,
            concern=concern,
            prior_claims=prior_claims,
        )
        normalized = normalize_answer(answer)
        outcome = client.extract_result(
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
        extraction = outcome.content
        source = "response_cache" if outcome.cache_hit else "fresh"
        resolved_pin.put(
            key,
            tool_input=extraction.model_dump(mode="json"),
            model_id=model_id,
            contract_version=EXTRACTOR_CONTRACT_VERSION,
        )
        # Adopting a concurrent writer's canonical row does not make this a
        # replay: this turn either called the model or replayed a cached
        # response, and that is what `source` records.
        canonical = resolved_pin.get(key)
        if canonical is not None:
            extraction = Extraction.model_validate(canonical)

    anchored = reanchor_spans(extraction, answer)
    grounded = drop_ungrounded(
        anchored,
        answer=answer,
        concern=concern,
        persona=persona,
        prior_answers=prior_answers,
        documents={
            SourceDocument.rfp_pws: content.rfp_text,
            SourceDocument.written_proposal: content.proposal_text,
        },
    )
    # Last of the three pure passes, and the only one that needs the authored
    # concern's `requires` tags. Runs after grounding so every link it reads
    # names a claim that survived. Its output is what gets scored, what decides
    # the follow-up, and what is persisted, so scoring and the report never see
    # an unenforced coverage row.
    checked = enforce_requires(grounded, concern)
    conciseness = compute_conciseness(answer, checked)
    return ExtractionResult(
        extraction=checked,
        conciseness=conciseness,
        provenance=ExtractionProvenance(
            source=source,
            key=key,
            contract_version=EXTRACTOR_CONTRACT_VERSION,
            model_id=model_id,
        ),
    )
