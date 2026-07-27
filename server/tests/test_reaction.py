"""Reaction-service tests (task 9).

The persona reply is generated AFTER the number is locked (anti-drift #1): the
prompt is rebuilt fresh from the persona file every turn and is handed the
already-computed ``support_delta`` and ``matched_rows`` so the reply describes
the number, never sets it. These tests use a fake BedrockClient — no network.
"""

from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from app.bedrock.cache import CacheKeyInput
from app.bedrock.client import BedrockClient
from app.content.loader import load_content
from app.pipeline.reaction import (
    build_reaction_prompt,
    run_clarification,
    run_reaction,
)
from app.schemas.extraction import (
    Backing,
    Claim,
    ClaimType,
    Dodge,
    DodgeType,
    Extraction,
    RedLineHit,
    RedLineSourceKind,
)
from app.schemas.reaction import PersonaReaction
from app.schemas.scoring import ScoreOutput


class FakeBedrockClient:
    def __init__(self, result: PersonaReaction) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def extract(
        self,
        content: str | list,
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


def _fixture() -> tuple[Any, Any]:
    content = load_content()
    persona = content.personas["technical_evaluator"]
    concern = content.concerns["technical_approach"]
    return persona, concern


def _extraction() -> Extraction:
    return Extraction(
        claims=[
            Claim(
                text="Named PM leads the effort.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="a named PM with twelve years",
            )
        ]
    )


def test_prompt_carries_persona_voice_and_the_locked_number() -> None:
    persona, concern = _fixture()
    score = ScoreOutput(support_delta=2, matched_rows=["evidence_backed"], capped=False)

    prompt = build_reaction_prompt(
        persona=persona,
        concern=concern,
        extraction=_extraction(),
        score=score,
    )

    # persona voice is rehydrated fresh so the reply stays in character
    assert persona.voice in prompt
    # the concern being reacted to is present
    assert concern.core_ask in prompt
    # the already-computed number and its matched rows are handed to the model,
    # sign included so the model can tell a gain from a loss
    assert "+2" in prompt
    assert "evidence_backed" in prompt
    # a positive turn must not claim a cap
    assert "cap" not in prompt.lower()


def test_prompt_renders_negative_sign_and_no_cap_when_uncapped() -> None:
    persona, concern = _fixture()
    score = ScoreOutput(support_delta=-1, matched_rows=["contradiction"], capped=False)

    prompt = build_reaction_prompt(
        persona=persona,
        concern=concern,
        extraction=_extraction(),
        score=score,
    )

    assert "-1" in prompt
    # a loss that did not cross a red line must not mention a cap
    assert "cap" not in prompt.lower()


def test_prompt_renders_none_when_no_rows_matched() -> None:
    persona, concern = _fixture()
    score = ScoreOutput(support_delta=0, matched_rows=[], capped=False)

    prompt = build_reaction_prompt(
        persona=persona,
        concern=concern,
        extraction=_extraction(),
        score=score,
    )

    assert "(none)" in prompt


def test_prompt_states_the_cap_when_capped() -> None:
    persona, concern = _fixture()
    score = ScoreOutput(support_delta=-2, matched_rows=["red_line"], capped=True)

    prompt = build_reaction_prompt(
        persona=persona,
        concern=concern,
        extraction=_extraction(),
        score=score,
    )

    assert "red_line" in prompt
    # the reply must know the red line was crossed
    assert "cap" in prompt.lower()


def test_prompt_summarizes_extraction_without_full_json_dump() -> None:
    persona, concern = _fixture()
    score = ScoreOutput(support_delta=-2, matched_rows=["red_line"], capped=True)
    extraction = Extraction(
        claims=[
            Claim(
                text="Named PM leads the effort.",
                type=ClaimType.commitment,
                backing=Backing.backed,
                span="a named PM with twelve years",
            )
        ],
        dodges=[
            Dodge(
                sub_question_id="staffing",
                type=DodgeType.topic_switch,
                evidence="pivoted to timeline",
            )
        ],
        red_line_hits=[
            RedLineHit(
                source_id="key_personnel",
                source_kind=RedLineSourceKind.concern_red_line,
                span="we may substitute leads",
                why="Named key personnel are not guaranteed.",
            )
        ],
    )

    prompt = build_reaction_prompt(
        persona=persona,
        concern=concern,
        extraction=extraction,
        score=score,
    )

    # the qualitative shape the reply references is present
    assert "Named PM leads the effort." in prompt
    assert "topic_switch" in prompt
    assert "Named key personnel are not guaranteed." in prompt
    # the verbose full-object JSON dump is gone
    assert '"sub_question_coverage"' not in prompt
    assert '"backing":' not in prompt


def test_run_reaction_returns_validated_persona_reaction() -> None:
    persona, concern = _fixture()
    score = ScoreOutput(support_delta=1, matched_rows=["approach_cited"], capped=False)
    canned = PersonaReaction(
        in_character_reply="Good, you cited the phased approach. Now defend the staffing.",
        rationale="Cited a compliant element of the approach; +1 support.",
    )
    client = FakeBedrockClient(canned)

    result = run_reaction(
        persona=persona,
        concern=concern,
        extraction=_extraction(),
        score=score,
        client=client,
    )

    assert isinstance(result, PersonaReaction)
    assert result == canned
    # the service forces the PersonaReaction schema through the tool
    call = client.calls[0]
    assert call["content_schema"] is PersonaReaction
    assert call["tool_name"] == "emit_reaction"


# --- normalized cache-key acceptance for run_clarification (uses the real
# BedrockClient.react over a DictCache, mirroring test_bedrock_client.py) ---


def _text_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn"
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
    """In-memory ``ResponseCache`` matching ``test_bedrock_client.py``'s."""

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


def test_clarification_variant_hits_the_same_cache_entry() -> None:
    persona, concern = _fixture()
    transport = _ScriptedTransport(
        _text_response("First reply."), _text_response("Different reply.")
    )
    client = BedrockClient(transport=transport, cache=DictCache())

    first = run_clarification(
        persona=persona,
        concern=concern,
        question="What counts as evidence here?",
        client=client,
    )
    second = run_clarification(
        persona=persona,
        concern=concern,
        question="  WHAT counts   as evidence here?  ",
        client=client,
    )

    assert first == second == "First reply."
    assert len(transport.calls) == 1
