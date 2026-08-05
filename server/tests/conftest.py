"""Shared test-double helpers.

``run_extraction`` calls ``BedrockClient.extract_result``, which reports whether
a response was replayed from ``model_response_cache``. The suite's doubles
implement ``extract`` only, so this mixin derives the other from it.
"""

from typing import Any

from app.bedrock.client import ExtractOutcome


class ExtractResultFromExtract:
    """Gives a double ``extract_result`` for free: whatever its own ``extract``
    returns, never a cache hit. A double has no response cache to hit.

    A double that wants to exercise the replay path overrides ``extract_result``
    directly (see ``CacheHitBedrockClient`` in ``test_extraction.py``).
    """

    def extract(self, content: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("mixin: the double supplies its own extract")

    def extract_result(self, content: Any, **kwargs: Any) -> ExtractOutcome[Any]:
        return ExtractOutcome(content=self.extract(content, **kwargs), cache_hit=False)
