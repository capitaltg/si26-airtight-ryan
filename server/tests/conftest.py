"""Shared test-double helpers.

``run_extraction`` calls ``BedrockClient.extract_result``, which reports whether
a response was replayed from ``model_response_cache``. The suite's doubles
implement ``extract`` only, so this mixin derives the other from it.
"""

from typing import Any

from pydantic import BaseModel

from app.bedrock.cache import CacheKeyInput
from app.bedrock.client import ExtractOutcome


class ExtractResultFromExtract:
    """Gives a double ``extract_result`` for free: whatever its own ``extract``
    returns, never a cache hit. A double has no response cache to hit.

    A double that wants to exercise the replay path overrides ``extract_result``
    directly (see ``CacheHitBedrockClient`` in ``test_extraction.py``).
    """

    def extract(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> BaseModel:
        raise NotImplementedError("mixin: the double supplies its own extract")

    def extract_result(
        self,
        content: str | list[Any],
        *,
        content_schema: type[BaseModel],
        tool_name: str,
        max_tokens: int = 4096,
        cache_key: CacheKeyInput | None = None,
    ) -> ExtractOutcome[BaseModel]:
        return ExtractOutcome(
            content=self.extract(
                content,
                content_schema=content_schema,
                tool_name=tool_name,
                max_tokens=max_tokens,
                cache_key=cache_key,
            ),
            cache_hit=False,
        )
