"""Extraction-service tests (task 7, step 5).

The prompt builder rehydrates the authored content fresh every turn (anti-drift
guardrail #1): the persona, the RFP + proposal, the active concern, and the
running claim ledger with its verbatim spans so Tier-0 contradictions can be
detected. These tests use a fake BedrockClient — no network.
"""

from typing import Any

from pydantic import BaseModel

from app.content.loader import load_content
from app.db.models import ClaimLedger
from app.pipeline.extraction import (
    ExtractionResult,
    build_extraction_dynamic_suffix,
    build_extraction_prompt,
    build_extraction_static_prefix,
    run_extraction,
)
from app.schemas.extraction import Backing, Claim, ClaimType, Extraction


class FakeBedrockClient:
    def __init__(self, result: Extraction) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def extract(
        self,
        content: str | list,
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
    ) -> BaseModel:
        self.calls.append(
            {
                "content": content,
                "content_schema": content_schema,
                "tool_name": tool_name,
            }
        )
        return self._result


def _fixture() -> tuple[Any, Any, Any]:
    content = load_content()
    persona = content.personas["technical_evaluator"]
    concern = content.concerns["technical_approach"]
    return content, persona, concern


def _prior_claims() -> list[ClaimLedger]:
    return [
        ClaimLedger(
            session_id=None,
            turn_index=0,
            text="The PM has 12 years of federal case-management experience.",
            type="commitment",
            backing="backed",
            span="twelve years running federal case systems",
        ),
        ClaimLedger(
            session_id=None,
            turn_index=1,
            text="We staff three named leads on day one.",
            type="commitment",
            backing="specified",
            span="three named leads staffed at contract start",
        ),
    ]


def test_prompt_rehydrates_persona_concern_and_prior_spans() -> None:
    content, persona, concern = _fixture()
    prior = _prior_claims()
    answer = "We follow a phased approach with two-week sprints and a named PM."

    prompt = build_extraction_prompt(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=prior,
    )

    # persona voice + concern ask are rehydrated verbatim
    assert persona.voice in prompt
    assert concern.core_ask in prompt
    # RFP and proposal are present so the model can ground fact checks
    assert content.rfp_text.strip()[:40] in prompt
    assert content.proposal_text.strip()[:40] in prompt
    # prior claim spans appear verbatim for Tier-0 consistency
    for row in prior:
        assert row.span in prompt
    # the answer under evaluation is included
    assert answer in prompt


def test_static_prefix_holds_cacheable_context() -> None:
    content, persona, concern = _fixture()

    prefix = build_extraction_static_prefix(persona=persona, content=content)

    # the cacheable prefix carries the turn-invariant context
    assert persona.voice in prefix
    assert content.rfp_text.strip()[:40] in prefix
    assert content.proposal_text.strip()[:40] in prefix
    # ...and none of the turn-varying rebuild
    assert concern.core_ask not in prefix


def test_dynamic_suffix_holds_the_anti_drift_rebuild() -> None:
    content, persona, concern = _fixture()
    prior = _prior_claims()
    answer = "We follow a phased approach with two-week sprints and a named PM."

    suffix = build_extraction_dynamic_suffix(
        answer=answer, concern=concern, prior_claims=prior
    )

    # the concern, the ledger spans, and the answer are sent fresh every turn
    assert concern.core_ask in suffix
    for row in prior:
        assert row.span in suffix
    assert answer in suffix
    # the cacheable context must not leak into the uncached suffix
    assert persona.voice not in suffix
    assert content.rfp_text.strip()[:40] not in suffix


def test_run_extraction_sends_cached_prefix_and_uncached_suffix() -> None:
    content, persona, concern = _fixture()
    prior = _prior_claims()
    answer = "We follow a phased approach with two-week sprints and a named PM."
    client = FakeBedrockClient(
        Extraction(
            claims=[
                Claim(
                    text="Named PM leads the effort.",
                    type=ClaimType.commitment,
                    backing=Backing.specified,
                    span="a named PM",
                )
            ]
        )
    )

    run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=prior,
        client=client,
    )

    blocks = client.calls[0]["content"]
    assert isinstance(blocks, list) and len(blocks) == 2
    prefix, suffix = blocks
    # the static prefix carries the cache breakpoint and the cacheable context
    assert prefix["cache_control"] == {"type": "ephemeral"}
    assert persona.voice in prefix["text"]
    assert content.rfp_text.strip()[:40] in prefix["text"]
    assert content.proposal_text.strip()[:40] in prefix["text"]
    # the dynamic suffix is uncached and carries the anti-drift rebuild
    assert "cache_control" not in suffix
    assert concern.core_ask in suffix["text"]
    assert answer in suffix["text"]
    for row in prior:
        assert row.span in suffix["text"]


def test_prompt_handles_empty_ledger() -> None:
    content, persona, concern = _fixture()
    prompt = build_extraction_prompt(
        answer="First answer of the session.",
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
    )
    assert concern.core_ask in prompt


def test_run_extraction_returns_extraction_plus_computed_conciseness() -> None:
    content, persona, concern = _fixture()
    canned = Extraction(
        claims=[
            Claim(
                text="Named PM leads the effort.",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="a named PM",
            )
        ]
    )
    client = FakeBedrockClient(canned)
    answer = "We follow a phased approach with two-week sprints and a named PM."

    result = run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        client=client,
    )

    assert isinstance(result, ExtractionResult)
    assert result.extraction == canned
    # conciseness is code-computed and attached, never model-emitted
    assert result.conciseness.word_count > 0
    # the service forces the Extraction schema through the tool
    call = client.calls[0]
    assert call["content_schema"] is Extraction
    assert call["tool_name"] == "record_extraction"
