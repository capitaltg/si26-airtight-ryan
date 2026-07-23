"""Single choke point for every Bedrock call.

Extraction is forced through tool-use, validated against a Pydantic model,
retried once, then fails loud. Unvalidated model JSON never reaches the scorer
(AGENTS.md locked constraints). Both methods pin the configured model id and
send ``temperature=0``.
"""

import logging
from typing import Any, Protocol, TypeVar, cast

from anthropic import AnthropicBedrock
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_ATTEMPTS = 2  # initial call + one retry


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
    def __init__(self, transport: Transport | None = None) -> None:
        # Credentials come from the standard AWS chain, never from code. The
        # cast is needed because the real client's `messages.create` is a set of
        # overloads rather than the **kwargs shape this wrapper calls it with.
        self._transport: Transport = transport or cast(
            Transport, AnthropicBedrock(aws_region=settings.aws_region)
        )

    def extract(
        self,
        content: str | list[dict[str, Any]],
        *,
        content_schema: type[ModelT],
        tool_name: str,
        max_tokens: int = 4096,
    ) -> ModelT:
        """Force `tool_name`, validate its input, retry once, then raise.

        ``content`` is either a plain string (wrapped as a single text block) or
        a pre-built list of content blocks. A caller passing blocks can place a
        ``cache_control`` breakpoint on the static prefix so Bedrock reuses it
        across turns; the block list is re-sent verbatim on retry, so the cache
        still applies.
        """
        blocks: list[dict[str, Any]] = (
            [{"type": "text", "text": content}] if isinstance(content, str) else content
        )
        tool = {
            "name": tool_name,
            "description": f"Record the structured {tool_name} for this turn.",
            "input_schema": content_schema.model_json_schema(),
        }
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
                return content_schema.model_validate(block.input)
            except ValidationError as exc:
                last = exc

        raise ExtractionValidationError(str(last)) from last

    def react(self, prompt: str, *, max_tokens: int = 1024) -> str:
        """Plain-text persona reply. Runs only after the score already exists."""
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
        return text
