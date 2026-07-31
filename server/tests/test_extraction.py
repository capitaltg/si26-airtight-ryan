"""Extraction-service tests (task 7, step 5).

The prompt builder rehydrates the authored content fresh every turn (anti-drift
guardrail #1): the persona, the RFP + proposal, the active concern, and the
running claim ledger with its verbatim spans so Tier-0 contradictions can be
detected. These tests use a fake BedrockClient — no network.
"""

from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from app.bedrock.cache import CacheKeyInput
from app.bedrock.client import BedrockClient
from app.content.loader import load_content
from app.db.models import ClaimLedger
from app.pipeline.extraction import (
    ExtractionResult,
    build_extraction_dynamic_suffix,
    build_extraction_prompt,
    build_extraction_static_prefix,
    run_extraction,
)
from app.pipeline.extraction_pin import InMemoryExtractionPin
from app.pipeline.scoring import score_turn
from app.schemas.extraction import Backing, Claim, ClaimType, Extraction


class FakeBedrockClient:
    def __init__(self, result: Extraction) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def extract(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        self.calls.append(
            {
                "content": content,
                "content_schema": content_schema,
                "tool_name": tool_name,
                "cache_key": cache_key,
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


# --- normalized cache-key acceptance: whitespace/case variants replay, wording
# and context changes still miss (server/app/bedrock/cache.py normalize_answer) ---


def _cache_block(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(**fields)


def _cache_tool_response(tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[_cache_block(type="tool_use", name="record_extraction", input=tool_input)],
        stop_reason="tool_use",
    )


class _ScriptedMessages:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _ScriptedTransport:
    def __init__(self, *responses: Any) -> None:
        self.messages = _ScriptedMessages(list(responses))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


class DictCache:
    """In-memory ``ResponseCache`` with first-write-wins ``put``, matching the
    DB-backed cache's contract without a database (mirrors
    ``test_bedrock_client.py``'s ``DictCache``)."""

    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self.store.get(key)

    def put(
        self,
        key: str,
        method: str,
        value: dict,
        normalized_answer: str | None = None,
    ) -> None:
        self.store.setdefault(key, value)


def _distinct_extraction_a() -> dict:
    return {
        "claims": [
            {
                "text": "PM has 12 years of federal experience.",
                "type": "commitment",
                "backing": "backed",
                "span": "our PM brings 12 years",
            }
        ]
    }


def _distinct_extraction_b() -> dict:
    return {
        "claims": [
            {
                "text": "Team delivered three prior systems.",
                "type": "commitment",
                "backing": "backed",
                "span": "three prior systems",
            }
        ]
    }


def _run(
    client: BedrockClient,
    answer: str,
    *,
    persona: Any = None,
    prior_claims: list[ClaimLedger] | None = None,
) -> ExtractionResult:
    content, default_persona, concern = _fixture()
    return run_extraction(
        answer=answer,
        concern=concern,
        persona=persona if persona is not None else default_persona,
        content=content,
        prior_claims=prior_claims if prior_claims is not None else [],
        client=client,
    )


def test_whitespace_variant_answer_hits_the_same_cache_entry() -> None:
    transport = _ScriptedTransport(
        _cache_tool_response(_distinct_extraction_a()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())
    answer = "We follow a phased approach with a named PM."
    whitespace_variant = "  We follow a phased  approach\twith a named   PM.  \n"

    first = _run(client, answer)
    second = _run(client, whitespace_variant)

    assert first.extraction == second.extraction
    assert len(transport.calls) == 1


def test_case_variant_answer_hits_the_same_cache_entry() -> None:
    transport = _ScriptedTransport(
        _cache_tool_response(_distinct_extraction_a()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())
    answer = "We follow a phased approach with a named PM."
    case_variant = "WE FOLLOW A PHASED APPROACH WITH A NAMED PM."

    first = _run(client, answer)
    second = _run(client, case_variant)

    assert first.extraction == second.extraction
    assert len(transport.calls) == 1


def test_reworded_answer_misses_the_cache() -> None:
    transport = _ScriptedTransport(
        _cache_tool_response(_distinct_extraction_a()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())

    _run(client, "We follow a phased approach with a named PM.")
    _run(client, "We follow a staged approach with a named PM.")

    assert len(transport.calls) == 2


def test_accidentally_joined_words_miss_the_cache() -> None:
    """Collapsing whitespace runs never deletes a word boundary, so a typo that
    runs two words together is a different token stream and keys apart. That is
    the safe outcome: a fresh model call reads the text as typed instead of
    replaying an extraction of the spaced phrasing."""
    transport = _ScriptedTransport(
        _cache_tool_response(_distinct_extraction_a()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())

    _run(client, "We follow a phased approach with a named PM.")
    _run(client, "We follow a phased approach with a namedPM.")

    assert len(transport.calls) == 2


def test_persona_change_still_misses_the_cache() -> None:
    """Same normalized answer, different persona: proves normalization did not
    leak past the answer into the cacheable prefix."""
    content = load_content()
    persona_a = content.personas["technical_evaluator"]
    persona_b = content.personas["contracting_officer"]
    transport = _ScriptedTransport(
        _cache_tool_response(_distinct_extraction_a()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())
    answer = "We follow a phased approach with a named PM."

    _run(client, answer, persona=persona_a)
    _run(client, answer, persona=persona_b)

    assert len(transport.calls) == 2


def test_prior_claims_change_still_misses_the_cache() -> None:
    """Same normalized answer, different claim ledger: the ledger stays
    byte-exact in the key, so a changed ledger still misses."""
    transport = _ScriptedTransport(
        _cache_tool_response(_distinct_extraction_a()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())
    answer = "We follow a phased approach with a named PM."

    _run(client, answer, prior_claims=[])
    _run(client, answer, prior_claims=_prior_claims())

    assert len(transport.calls) == 2


# --- a replayed extraction must still quote the answer on screen
# (server/app/pipeline/span_anchor.py) ---

_ANCHOR_ANSWER = "We follow a phased approach. Our PM has 12 years of federal work."


def _quoting_extraction() -> dict:
    """An extraction whose span is quoted verbatim out of ``_ANCHOR_ANSWER``, the
    way the model is instructed to quote."""
    return {
        "claims": [
            {
                "text": "PM has 12 years of federal experience.",
                "type": "commitment",
                "backing": "backed",
                "span": "Our PM has 12 years of federal work",
            }
        ]
    }


def test_replayed_span_is_reanchored_to_the_answer_actually_typed() -> None:
    """The cache hit is the point, but the replayed span was quoted out of the
    first phrasing. Without re-anchoring the transcript shows one text and the
    report quotes another."""
    transport = _ScriptedTransport(
        _cache_tool_response(_quoting_extraction()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())
    variant = "  we follow a phased   approach.\tour pm HAS 12 years of federal work. "

    first = _run(client, _ANCHOR_ANSWER)
    second = _run(client, variant)

    assert len(transport.calls) == 1  # still a cache hit
    assert first.extraction.claims[0].span == "Our PM has 12 years of federal work"
    assert second.extraction.claims[0].span == "our pm HAS 12 years of federal work"
    assert second.extraction.claims[0].span in variant


def test_reanchoring_does_not_move_the_scored_signals() -> None:
    """Re-anchoring rewrites quote text only, so the fields the scorer reads come
    through identical and the two runs score the same."""
    transport = _ScriptedTransport(
        _cache_tool_response(_quoting_extraction()),
        _cache_tool_response(_distinct_extraction_b()),
    )
    client = BedrockClient(transport=transport, cache=DictCache())

    first = _run(client, _ANCHOR_ANSWER)
    second = _run(client, _ANCHOR_ANSWER.upper())

    assert len(transport.calls) == 1  # the same cached extraction backs both
    for a, b in zip(first.extraction.claims, second.extraction.claims, strict=True):
        assert (a.text, a.type, a.backing) == (b.text, b.type, b.backing)


def test_cold_call_leaves_the_models_own_span_untouched() -> None:
    """No cache involved: the span the model just quoted is already a substring of
    the answer, so re-anchoring must not rewrite it."""
    client = FakeBedrockClient(
        Extraction.model_validate(_quoting_extraction())
    )
    result = _run(client, _ANCHOR_ANSWER)  # type: ignore[arg-type]

    assert result.extraction.claims[0].span == "Our PM has 12 years of federal work"


class ScriptedBedrockClient:
    """Returns a different extraction on each call, to prove the pin holds."""

    def __init__(self, results: list[Extraction]) -> None:
        self._results = list(results)
        self.calls = 0

    def extract(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        self.calls += 1
        return self._results.pop(0)


_GROUNDED_ANSWER = "We staff three named leads at contract start."


def _clean_extraction() -> Extraction:
    return Extraction(
        claims=[
            Claim(
                text="Three named leads at contract start.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="three named leads at contract start",
            )
        ]
    )


def _harsher_extraction() -> Extraction:
    """Same answer, but the model decided it was a bare promise this time."""
    return Extraction(
        claims=[
            Claim(
                text="Three named leads at contract start.",
                type=ClaimType.commitment,
                backing=Backing.bare,
                span="three named leads at contract start",
            )
        ]
    )


def test_same_input_scores_the_same_when_the_model_disagrees_with_itself() -> None:
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction(), _harsher_extraction()])
    pin = InMemoryExtractionPin()

    def once() -> int:
        result = run_extraction(
            answer=_GROUNDED_ANSWER,
            concern=concern,
            persona=persona,
            content=content,
            prior_claims=[],
            client=client,  # type: ignore[arg-type]
            pin=pin,
        )
        return score_turn(result.extraction, content.rubric).support_delta

    first = once()
    second = once()
    assert first == second
    assert client.calls == 1, "the second run must not reach the model"


def test_whitespace_variant_of_the_same_answer_replays_the_pin() -> None:
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction(), _harsher_extraction()])
    pin = InMemoryExtractionPin()
    run_extraction(
        answer=_GROUNDED_ANSWER,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        client=client,  # type: ignore[arg-type]
        pin=pin,
    )
    run_extraction(
        answer="  We  STAFF three named\nleads at contract start. ",
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        client=client,  # type: ignore[arg-type]
        pin=pin,
    )
    assert client.calls == 1


def test_a_rubric_change_rescores_without_touching_the_model() -> None:
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction()])
    pin = InMemoryExtractionPin()
    result = run_extraction(
        answer=_GROUNDED_ANSWER,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        client=client,  # type: ignore[arg-type]
        pin=pin,
    )
    baseline = score_turn(result.extraction, content.rubric).support_delta
    bumped_rows = [
        row.model_copy(update={"support_value": row.support_value - 1})
        if row.id == "evidence_backed"
        else row
        for row in content.rubric.rows
    ]
    bumped = content.rubric.model_copy(update={"rows": bumped_rows})
    assert score_turn(result.extraction, bumped).support_delta != baseline
    assert client.calls == 1


def test_run_extraction_grounds_before_scoring() -> None:
    content, persona, concern = _fixture()
    fabricated = Extraction(
        claims=[
            Claim(
                text="invented",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="a quote the presenter never typed",
            )
        ]
    )
    client = ScriptedBedrockClient([fabricated])
    result = run_extraction(
        answer=_GROUNDED_ANSWER,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        client=client,  # type: ignore[arg-type]
    )
    assert result.extraction.claims == []
    assert score_turn(result.extraction, content.rubric).support_delta == 0


def test_pin_defaults_to_null_so_existing_callers_are_unpinned() -> None:
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction(), _harsher_extraction()])
    for _ in range(2):
        run_extraction(
            answer=_GROUNDED_ANSWER,
            concern=concern,
            persona=persona,
            content=content,
            prior_claims=[],
            client=client,  # type: ignore[arg-type]
        )
    assert client.calls == 2
