from types import SimpleNamespace
from typing import Any

import pytest

from app.bedrock.client import BedrockClient, ExtractionValidationError
from app.config import settings
from app.schemas.extraction import Extraction


def _block(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(**fields)


def _tool_response(tool_input: dict, stop_reason: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(
        content=[_block(type="tool_use", name="record_extraction", input=tool_input)],
        stop_reason=stop_reason,
    )


def _text_response(*texts: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=[_block(type="text", text=t) for t in texts],
        stop_reason=stop_reason,
    )


class FakeMessages:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("transport called more times than scripted")
        return self._responses.pop(0)


class FakeTransport:
    def __init__(self, *responses: Any) -> None:
        self.messages = FakeMessages(list(responses))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


def _valid_input() -> dict:
    return {
        "claims": [
            {
                "text": "The PM has 12 years of federal case-management experience.",
                "type": "commitment",
                "backing": "backed",
                "span": "our PM brings 12 years running federal case systems",
            }
        ]
    }


def _extract(client: BedrockClient) -> Extraction:
    return client.extract("prompt", content_schema=Extraction, tool_name="record_extraction")


def test_valid_tool_input_returns_validated_instance() -> None:
    transport = FakeTransport(_tool_response(_valid_input()))
    ext = _extract(BedrockClient(transport=transport))
    assert isinstance(ext, Extraction)
    assert ext.claims[0].backing is not None
    assert len(transport.calls) == 1


def test_two_invalid_responses_raise_after_exactly_two_calls() -> None:
    bad = {"claims": [{"text": "x", "type": "not_a_claim_type", "span": "x"}]}
    transport = FakeTransport(_tool_response(bad), _tool_response(bad))
    with pytest.raises(ExtractionValidationError):
        _extract(BedrockClient(transport=transport))
    assert len(transport.calls) == 2


def test_retry_succeeds_on_second_response() -> None:
    bad = {"hallucinated_field": "surprise"}
    transport = FakeTransport(_tool_response(bad), _tool_response(_valid_input()))
    ext = _extract(BedrockClient(transport=transport))
    assert ext.claims[0].type.value == "commitment"
    assert len(transport.calls) == 2


def test_missing_tool_use_block_raises() -> None:
    transport = FakeTransport(_text_response("I would rather chat."), _text_response("Still no."))
    with pytest.raises(ExtractionValidationError):
        _extract(BedrockClient(transport=transport))


def test_truncated_response_raises_without_burning_the_retry() -> None:
    # a max_tokens stop means the tool JSON is cut mid-object; retrying repeats it
    transport = FakeTransport(_tool_response(_valid_input(), stop_reason="max_tokens"))
    with pytest.raises(ExtractionValidationError):
        _extract(BedrockClient(transport=transport))
    assert len(transport.calls) == 1


def test_extract_forces_the_tool_with_temperature_zero_and_pinned_model() -> None:
    transport = FakeTransport(_tool_response(_valid_input()))
    _extract(BedrockClient(transport=transport))
    kwargs = transport.calls[0]
    assert kwargs["temperature"] == 0
    assert kwargs["model"] == settings.bedrock_model_id
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_extraction"}
    schema = kwargs["tools"][0]["input_schema"]
    assert schema["additionalProperties"] is False
    assert "conciseness" not in schema["properties"]


def test_react_returns_concatenated_text() -> None:
    transport = FakeTransport(_text_response("Dana here. ", "Walk me through staffing."))
    reply = BedrockClient(transport=transport).react("prompt")
    assert reply == "Dana here. Walk me through staffing."
    kwargs = transport.calls[0]
    assert kwargs["temperature"] == 0
    assert kwargs["model"] == settings.bedrock_model_id
    assert "tools" not in kwargs


def test_react_raises_on_empty_text() -> None:
    transport = FakeTransport(_text_response(stop_reason="refusal"))
    with pytest.raises(ExtractionValidationError):
        BedrockClient(transport=transport).react("prompt")


class DictCache:
    """In-memory ``ResponseCache`` with first-write-wins ``put``, matching the
    DB-backed cache's contract without a database."""

    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self.store.get(key)

    def put(self, key: str, method: str, value: dict) -> None:
        self.store.setdefault(key, value)


def _other_valid_input() -> dict:
    """A second, distinct valid extraction — stands in for the model returning
    different output on an identical request (the bug this cache fixes)."""
    return {
        "claims": [
            {
                "text": "The team has run three prior federal case-management systems.",
                "type": "commitment",
                "backing": "backed",
                "span": "we have delivered three federal case systems",
            }
        ]
    }


def test_extract_replays_first_response_for_identical_request() -> None:
    # Transport is scripted to return DIFFERENT valid output on the two calls;
    # with a cache the second identical request must replay the first and not
    # touch the transport at all.
    transport = FakeTransport(
        _tool_response(_valid_input()), _tool_response(_other_valid_input())
    )
    client = BedrockClient(transport=transport, cache=DictCache())

    first = _extract(client)
    second = _extract(client)

    assert first == second
    assert len(transport.calls) == 1  # second answer came from the cache


def test_extract_does_not_cache_an_invalid_response() -> None:
    # First response is invalid (retry saves it); only the validated success is
    # stored, so a fresh identical request replays the good one in one call.
    bad = {"claims": [{"text": "x", "type": "not_a_claim_type", "span": "x"}]}
    cache = DictCache()
    transport = FakeTransport(_tool_response(bad), _tool_response(_valid_input()))
    first = _extract(BedrockClient(transport=transport, cache=cache))
    assert len(transport.calls) == 2  # burned the retry on the invalid one

    replay_transport = FakeTransport()  # would raise if called
    second = _extract(BedrockClient(transport=replay_transport, cache=cache))
    assert second == first
    assert len(replay_transport.calls) == 0


def test_react_replays_first_response_for_identical_request() -> None:
    transport = FakeTransport(_text_response("First reply."), _text_response("Different."))
    client = BedrockClient(transport=transport, cache=DictCache())

    first = client.react("prompt")
    second = client.react("prompt")

    assert first == second == "First reply."
    assert len(transport.calls) == 1


def test_react_does_not_cache_empty_text() -> None:
    cache = DictCache()
    empty = FakeTransport(_text_response(stop_reason="refusal"))
    with pytest.raises(ExtractionValidationError):
        BedrockClient(transport=empty, cache=cache).react("prompt")

    good = FakeTransport(_text_response("Now a real reply."))
    reply = BedrockClient(transport=good, cache=cache).react("prompt")
    assert reply == "Now a real reply."


def test_cache_keys_differ_by_prompt() -> None:
    transport = FakeTransport(_text_response("A reply."), _text_response("B reply."))
    client = BedrockClient(transport=transport, cache=DictCache())
    assert client.react("prompt A") == "A reply."
    assert client.react("prompt B") == "B reply."
    assert len(transport.calls) == 2  # distinct prompts, no false cache hit
