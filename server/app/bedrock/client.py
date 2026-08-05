"""Single choke point for every Bedrock call.

Extraction is forced through tool-use, validated against a Pydantic model,
retried once, then fails loud. Unvalidated model JSON never reaches the scorer
(AGENTS.md locked constraints). ``extract_result`` also reports whether the
response was replayed from ``model_response_cache``; ``extract`` is the same call
without that flag. Every method pins the configured model id and sends
``temperature=0``.
"""

import logging
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast

from anthropic import AnthropicBedrock
from pydantic import BaseModel, ValidationError

from app.bedrock.cache import CacheKeyInput, ResponseCache, request_key
from app.config import settings

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_ATTEMPTS = 2  # initial call + one retry


@dataclass(frozen=True)
class ExtractOutcome(Generic[ModelT]):
    """The validated tool input plus how it got here.

    ``cache_hit`` is True only when ``model_response_cache`` replayed a stored
    response, so a caller can record whether this turn actually reached the
    model. ``extract`` drops it; ``run_extraction`` keeps it.
    """

    content: ModelT
    cache_hit: bool


class ExtractionValidationError(RuntimeError):
    """The model never produced tool input that validates against the schema."""


def _log_cache_usage(tool_name: str, usage: Any) -> None:
    """Emit prompt-cache token counts so cache hits are observable.

    Guarded with ``getattr`` because the test transport fakes return responses
    with no ``usage`` attribute.
    """
    if usage is None:
        return
    logger.debug(
        "bedrock %s usage: input=%s cache_write=%s cache_read=%s",
        tool_name,
        getattr(usage, "input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
    )


class MessagesProtocol(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class Transport(Protocol):
    """The slice of the Anthropic client this wrapper uses.

    Narrow on purpose: the test fake satisfies it without any anthropic types
    and without touching the network.
    """

    messages: MessagesProtocol


class BedrockClient:
    def __init__(
        self,
        transport: Transport | None = None,
        *,
        cache: ResponseCache | None = None,
    ) -> None:
        # Credentials come from the standard AWS chain, never from code. The
        # cast is needed because the real client's `messages.create` is a set of
        # overloads rather than the **kwargs shape this wrapper calls it with.
        self._transport: Transport = transport or cast(
            Transport, AnthropicBedrock(aws_region=settings.aws_region)
        )
        # When set, the first successful response for a given request is stored
        # and replayed on later identical requests, so a rehearsal is repeatable
        # despite temperature=0 not being reproducible on Bedrock. Left None (the
        # golden suite and unit tests) means every call hits the transport.
        self._cache = cache

    def extract_result(
        self,
        content: str | list[dict[str, Any]],
        *,
        content_schema: type[ModelT],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> ExtractOutcome[ModelT]:
        """Force `tool_name`, validate its input, retry once, then raise, and
        report whether the response came from the cache.

        ``content`` is either a plain string (wrapped as a single text block) or
        a pre-built list of content blocks. A caller passing blocks can place a
        ``cache_control`` breakpoint on the static prefix so Bedrock reuses it
        across turns; the block list is re-sent verbatim on retry, so the cache
        still applies.

        ``cache_key``, when given, supplies content to hash instead of
        ``content`` (and the normalized text to record on the row). The
        transport call below always sends ``content``/``blocks`` verbatim, so
        the model sees exactly what the caller built regardless of what gets
        hashed.
        """
        blocks: list[dict[str, Any]] = (
            [{"type": "text", "text": content}] if isinstance(content, str) else content
        )
        input_schema = content_schema.model_json_schema()
        tool = {
            "name": tool_name,
            "description": f"Record the structured {tool_name} for this turn.",
            "input_schema": input_schema,
        }

        key: str | None = None
        if self._cache is not None:
            hashed = cache_key.content if cache_key is not None else content
            key = request_key(
                method="extract",
                model=settings.bedrock_model_id,
                max_tokens=max_tokens,
                content=hashed,
                tool_name=tool_name,
                schema=input_schema,
            )
            cached = self._cache.get(key)
            if cached is not None:
                # Replay: re-validate the stored tool input so the returned
                # object is byte-identical to the first run's, without a call.
                return ExtractOutcome(
                    content=content_schema.model_validate(cached["tool_input"]),
                    cache_hit=True,
                )

        last: Exception | None = None

        for _ in range(_ATTEMPTS):
            response = self._transport.messages.create(
                model=settings.bedrock_model_id,
                max_tokens=max_tokens,
                temperature=0,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": blocks}],
            )

            _log_cache_usage(tool_name, getattr(response, "usage", None))

            if getattr(response, "stop_reason", None) == "max_tokens":
                # Tool input is cut mid-JSON. A retry truncates identically, so
                # spending it here buys nothing.
                raise ExtractionValidationError(
                    f"{tool_name} response hit max_tokens; tool input is truncated"
                )

            block = next((b for b in response.content if b.type == "tool_use"), None)
            if block is None:
                last = ExtractionValidationError(
                    f"response carried no {tool_name} tool_use block"
                )
                continue

            try:
                validated = content_schema.model_validate(block.input)
            except ValidationError as exc:
                last = exc
                continue

            # Only a validated success is cached; an invalid response is never
            # pinned, so a later retry can still land a good result.
            if self._cache is not None and key is not None:
                self._cache.put(
                    key,
                    "extract",
                    {"tool_input": block.input},
                    normalized_answer=cache_key.normalized_answer if cache_key else None,
                )
            return ExtractOutcome(content=validated, cache_hit=False)

        raise ExtractionValidationError(str(last)) from last

    def extract(
        self,
        content: str | list[dict[str, Any]],
        *,
        content_schema: type[ModelT],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> ModelT:
        """:meth:`extract_result` without the provenance. Kept so callers that do
        not care whether the response was cached — ``run_reaction`` above all —
        need no change."""
        return self.extract_result(
            content,
            content_schema=content_schema,
            tool_name=tool_name,
            max_tokens=max_tokens,
            cache_key=cache_key,
        ).content

    def react(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        cache_key: CacheKeyInput | None = None,
    ) -> str:
        """Plain-text persona reply. Runs only after the score already exists.

        ``cache_key`` behaves as in :meth:`extract`: it changes only what gets
        hashed and recorded, never what gets sent to the model.
        """
        key: str | None = None
        if self._cache is not None:
            hashed = cache_key.content if cache_key is not None else prompt
            key = request_key(
                method="react",
                model=settings.bedrock_model_id,
                max_tokens=max_tokens,
                content=hashed,
            )
            cached = self._cache.get(key)
            if cached is not None:
                return cast(str, cached["text"])

        response = self._transport.messages.create(
            model=settings.bedrock_model_id,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        if not text.strip():
            # A refusal or an unexpected stop reason must not flow downstream as
            # a persona reply.
            raise ExtractionValidationError(
                f"reaction returned no text (stop_reason={getattr(response, 'stop_reason', None)})"
            )

        # Cache only the non-empty success, mirroring extract.
        if self._cache is not None and key is not None:
            self._cache.put(
                key,
                "react",
                {"text": text},
                normalized_answer=cache_key.normalized_answer if cache_key else None,
            )
        return text
