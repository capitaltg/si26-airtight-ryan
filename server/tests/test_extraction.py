"""Extraction-service tests (task 7, step 5).

The prompt builder rehydrates the authored content fresh every turn (anti-drift
guardrail #1): the persona, the RFP + proposal, the active concern, and the
running claim ledger with its verbatim spans so Tier-0 contradictions can be
detected. These tests use a fake BedrockClient — no network.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from app.bedrock.cache import CacheKeyInput
from app.bedrock.client import BedrockClient, ExtractOutcome
from app.config import settings
from app.content.loader import load_content
from app.db.models import ClaimLedger
from app.pipeline.extraction import (
    EXTRACTOR_CONTRACT_VERSION,
    ExtractionProvenance,
    ExtractionResult,
    build_extraction_dynamic_suffix,
    build_extraction_prompt,
    build_extraction_static_prefix,
    run_extraction,
)
from app.pipeline.extraction_pin import InMemoryExtractionPin, extraction_key
from app.pipeline.scoring import score_turn
from app.schemas.extraction import (
    Addressed,
    Backing,
    Claim,
    ClaimType,
    Extraction,
    SubQuestionCoverage,
)
from tests.conftest import ExtractResultFromExtract


class FakeBedrockClient(ExtractResultFromExtract):
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
        prior_answers={},
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


def test_prompt_renders_red_lines_and_non_negotiables_with_bracketed_ids() -> None:
    content = load_content()
    prompt = build_extraction_prompt(
        answer="We will host on premises.",
        concern=content.concerns["technical_approach"],
        persona=content.personas["technical_evaluator"],
        content=content,
        prior_claims=[],
    )
    assert "[on_prem_hosting] Proposes on-premises hosting" in prompt
    assert "[no_hand_waved_migration] do not hand-wave the migration" in prompt


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
        prior_answers={},
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


def test_run_extraction_demotes_coverage_whose_requires_contract_is_unmet() -> None:
    """key_personnel/pm_commitment requires a commitment. Link an empirical claim
    to it and the coverage must come back `none`."""
    content, persona, _ = _fixture()
    concern = content.concerns["key_personnel"]
    answer = "Karen Holloway has twelve years managing federal software programs."
    scripted = Extraction(
        claims=[
            Claim(
                text="twelve years of federal software programs",
                type=ClaimType.empirical_checkable,
                span="Karen Holloway has twelve years",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm_commitment",
                addressed=Addressed.full,
                span="Karen Holloway has twelve years",
                evidence_claim_spans=["Karen Holloway has twelve years"],
            )
        ],
    )
    result = run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
        client=FakeBedrockClient(scripted),
    )
    assert result.extraction.sub_question_coverage[0].addressed is Addressed.none


def test_run_extraction_keeps_coverage_whose_requires_contract_is_met() -> None:
    """The same shape with a commitment claim linked instead. Proves the demotion
    above is the contract firing, not the link being dropped."""
    content, persona, _ = _fixture()
    concern = content.concerns["key_personnel"]
    answer = "Karen Holloway is committed full-time for the base period."
    scripted = Extraction(
        claims=[
            Claim(
                text="full-time for the base period",
                type=ClaimType.commitment,
                backing=Backing.specified,
                span="Karen Holloway is committed full-time",
            )
        ],
        sub_question_coverage=[
            SubQuestionCoverage(
                id="pm_commitment",
                addressed=Addressed.full,
                span="Karen Holloway is committed full-time",
                evidence_claim_spans=["Karen Holloway is committed full-time"],
            )
        ],
    )
    result = run_extraction(
        answer=answer,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
        client=FakeBedrockClient(scripted),
    )
    assert result.extraction.sub_question_coverage[0].addressed is Addressed.full


def test_prompt_states_the_requires_contract_and_the_link_field() -> None:
    content, persona, concern = _fixture()
    prompt = build_extraction_prompt(
        answer="We run on AWS GovCloud.",
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
    )
    assert "evidence_claim_spans" in prompt
    assert "fact_or_commitment" in prompt
    assert "verdict: supported" in prompt
    # The rule belongs in the cached prefix, not the per-turn rebuild.
    prefix = build_extraction_static_prefix(persona=persona, content=content)
    assert "evidence_claim_spans" in prefix


def test_prompt_asks_for_the_coverage_span_it_later_enforces() -> None:
    """`SubQuestionCoverage.span` is optional in the schema but mandatory
    downstream: grounding discards a full/partial row without one, and the report
    only prints an approach_cited finding when it is set. The prompt has to ask
    for it, or the model leaves it null and real coverage is thrown away.
    """
    content, persona, _ = _fixture()
    prefix = build_extraction_static_prefix(persona=persona, content=content)
    coverage_rule = prefix.split("Coverage rules.")[1].split("Fact-check rules.")[0]
    # The row's own `span`, not the `span` the link field already borrows from a
    # claim -- those are different fields and the rule has to name both.
    assert "quote from the answer in `span`" in coverage_rule


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
        prior_answers={},
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


class ScriptedBedrockClient(ExtractResultFromExtract):
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


class SynchronizedRacingBedrockClient(ExtractResultFromExtract):
    """Makes two cold extraction calls return opposing valid findings."""

    def __init__(self) -> None:
        self._barrier = Barrier(2)
        self._lock = Lock()
        self._calls = 0

    def extract(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        with self._lock:
            self._calls += 1
            result = _clean_extraction() if self._calls == 1 else _harsher_extraction()
        self._barrier.wait(timeout=5)
        return result


class SynchronizedFirstWriterPin:
    """Forces two initial misses, then makes the clean extraction canonical."""

    def __init__(self) -> None:
        self._cold_gets = Barrier(2)
        self._clean_stored = Event()
        self._lock = Lock()
        self._get_calls = 0
        self._tool_input: dict[str, Any] | None = None

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            self._get_calls += 1
            is_cold_miss = self._get_calls <= 2
        if is_cold_miss:
            self._cold_gets.wait(timeout=5)
            return None
        with self._lock:
            return dict(self._tool_input) if self._tool_input is not None else None

    def put(
        self,
        key: str,
        *,
        tool_input: dict[str, Any],
        model_id: str,
        contract_version: int,
    ) -> None:
        is_clean = tool_input["claims"][0]["backing"] == Backing.backed
        if not is_clean:
            assert self._clean_stored.wait(timeout=5), "clean writer never stored"
        with self._lock:
            if self._tool_input is None:
                self._tool_input = dict(tool_input)
                self._clean_stored.set()


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
            prior_answers={},
            client=client,  # type: ignore[arg-type]
            pin=pin,
        )
        return score_turn(result.extraction, content.rubric).support_delta

    first = once()
    second = once()
    assert first == second
    assert client.calls == 1, "the second run must not reach the model"


def test_concurrent_first_misses_return_the_canonical_pinned_extraction() -> None:
    content, persona, concern = _fixture()
    client = SynchronizedRacingBedrockClient()
    pin = SynchronizedFirstWriterPin()

    def once() -> ExtractionResult:
        return run_extraction(
            answer=_GROUNDED_ANSWER,
            concern=concern,
            persona=persona,
            content=content,
            prior_claims=[],
            prior_answers={},
            client=client,  # type: ignore[arg-type]
            pin=pin,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=5) for future in (pool.submit(once), pool.submit(once))]

    assert [result.extraction for result in results] == [
        _clean_extraction(),
        _clean_extraction(),
    ]
    assert [score_turn(result.extraction, content.rubric).support_delta for result in results] == [
        2,
        2,
    ]


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
        prior_answers={},
        client=client,  # type: ignore[arg-type]
        pin=pin,
    )
    run_extraction(
        answer="  We  STAFF three named\nleads at contract start. ",
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
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
        prior_answers={},
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
        prior_answers={},
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
            prior_answers={},
            client=client,  # type: ignore[arg-type]
        )
    assert client.calls == 2


def test_prompt_renders_persona_exemplars_for_classification() -> None:
    """The hand-graded exemplars are the documented anti-drift lever (see
    tests/golden/test_golden.py). They were loaded, stored, and editable, but
    rendered into no prompt, so authoring one changed nothing.
    """
    content = load_content()
    persona = content.personas["program_rep"]
    prefix = build_extraction_static_prefix(persona=persona, content=content)
    assert "We are committed to a smooth transition and a great user experience." in prefix
    assert "Sentiment with no support model" in prefix


def test_contracting_officer_exemplars_separate_false_fact_from_the_red_line() -> None:
    """The calibration that settles `false_fact_pm_years` (golden suite).

    Without it the model graded an overstated number about a named PM as the
    `unsupported_experience` red line on roughly one live run in five, which caps
    the meter instead of charging a false fact. Deleting either exemplar reverts
    that, silently and only on the live suite, so assert both reach the prompt.
    """
    content = load_content()
    persona = content.personas["contracting_officer"]
    prefix = build_extraction_static_prefix(persona=persona, content=content)
    assert "Samuel Ortiz, has fourteen years in cloud-native" in prefix
    assert "Record that as a tier-1 refuted fact check" in prefix
    assert "Census Bureau data-lake rebuild" in prefix
    assert "unsupported_experience red line" in prefix


def test_exemplar_block_withholds_the_hand_graded_number() -> None:
    """Extraction never sees a score. The exemplars carry one, so the block
    renders the answer and the judgment and drops `support_delta` — otherwise
    wiring calibration in would hand the model the number the engine owns.
    """
    content = load_content()
    persona = content.personas["program_rep"]
    prefix = build_extraction_static_prefix(persona=persona, content=content)
    block = prefix.split("## Worked examples")[1]
    assert "support_delta" not in block


def test_extractor_contract_version_is_six() -> None:
    # v4 asked for `SubQuestionCoverage.span`, which the prompt had never
    # requested and grounding had been discarding every full/partial row for.
    # v5 renders the persona's worked exemplars. v6 adds two of them to
    # contracting_officer, separating an overstated number about named personnel
    # (a false fact) from experience the proposal never mentions (the red line).
    # All three change what the model is asked to report, so earlier pins must
    # miss rather than replay a judgment made under the old contract.
    assert EXTRACTOR_CONTRACT_VERSION == 6


def test_the_prompt_states_the_three_part_revision_bar() -> None:
    content = load_content()
    concern = content.concerns["risk"]
    suffix = build_extraction_dynamic_suffix(
        answer="Earlier I said data migration; profiling came back clean, so it is staffing now.",
        concern=concern,
        prior_claims=[],
    )
    assert "acknowledged_revision" in suffix
    # all three parts, or the bar is cheap enough to bolt onto a concealed flip
    assert "refers to the earlier position" in suffix
    assert "states the new position" in suffix
    assert "gives a reason for the change" in suffix


def _pin_key(content: Any, persona: Any, concern: Any, *, model_id: str) -> str:
    return extraction_key(
        answer=_GROUNDED_ANSWER,
        persona_id=persona.id,
        concern_id=concern.concern_id,
        prior_claims=[],
        prior_answers={},
        extraction_fingerprint=content.extraction_fingerprint,
        extractor_contract_version=EXTRACTOR_CONTRACT_VERSION,
        model_id=model_id,
    )


def test_a_model_change_calls_the_model_instead_of_replaying(monkeypatch: Any) -> None:
    """The documented invalidation policy, as a test. A model upgrade is a
    one-line config change: the old rows stay put and are simply unreachable."""
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction(), _harsher_extraction()])
    pin = InMemoryExtractionPin()
    original = settings.bedrock_model_id

    def once() -> None:
        run_extraction(
            answer=_GROUNDED_ANSWER,
            concern=concern,
            persona=persona,
            content=content,
            prior_claims=[],
            prior_answers={},
            client=client,  # type: ignore[arg-type]
            pin=pin,
        )

    once()
    assert client.calls == 1
    new_model = "us.anthropic.claude-sonnet-4-6-20260101-v1:0"
    monkeypatch.setattr(settings, "bedrock_model_id", new_model)
    once()
    assert client.calls == 2, "a model change must reach the model, not the pin"
    assert pin.get(_pin_key(content, persona, concern, model_id=original)) is not None, (
        "the pre-upgrade row is left in place for a targeted delete"
    )


class CacheHitBedrockClient(ExtractResultFromExtract):
    """A pin miss that lands on the response cache: reports the replay the real
    client reports, so no transport call happened."""

    def __init__(self, result: Extraction) -> None:
        self._result = result

    def extract(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        return self._result

    def extract_result(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> ExtractOutcome[BaseModel]:
        return ExtractOutcome(content=self._result, cache_hit=True)


def test_a_first_extraction_records_a_fresh_source() -> None:
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction()])
    result = run_extraction(
        answer=_GROUNDED_ANSWER,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
        client=client,  # type: ignore[arg-type]
        pin=InMemoryExtractionPin(),
    )
    assert result.provenance == ExtractionProvenance(
        source="fresh",
        key=_pin_key(content, persona, concern, model_id=settings.bedrock_model_id),
        contract_version=EXTRACTOR_CONTRACT_VERSION,
        model_id=settings.bedrock_model_id,
    )


def test_a_replayed_extraction_records_a_pin_source() -> None:
    content, persona, concern = _fixture()
    client = ScriptedBedrockClient([_clean_extraction(), _harsher_extraction()])
    pin = InMemoryExtractionPin()

    def once() -> ExtractionResult:
        return run_extraction(
            answer=_GROUNDED_ANSWER,
            concern=concern,
            persona=persona,
            content=content,
            prior_claims=[],
            prior_answers={},
            client=client,  # type: ignore[arg-type]
            pin=pin,
        )

    assert once().provenance.source == "fresh"
    assert once().provenance.source == "pin"
    assert client.calls == 1


def test_a_response_cache_replay_records_a_response_cache_source() -> None:
    """The pin missed and the model was never called: the stored response came
    back instead. Recorded distinctly so "did this turn cost a model call" has an
    answer in the database."""
    content, persona, concern = _fixture()
    result = run_extraction(
        answer=_GROUNDED_ANSWER,
        concern=concern,
        persona=persona,
        content=content,
        prior_claims=[],
        prior_answers={},
        client=CacheHitBedrockClient(_clean_extraction()),  # type: ignore[arg-type]
        pin=InMemoryExtractionPin(),
    )
    assert result.provenance.source == "response_cache"
