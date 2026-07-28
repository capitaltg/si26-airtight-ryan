"""Wraps the `amazon-transcribe` streaming SDK behind a plain sync function.

The SDK is asyncio-only, but this module's public function is a plain `def`:
FastAPI runs sync route handlers in a threadpool, so `asyncio.run` inside a
`def` is safe there (no event loop is already running on that thread), and it
keeps the public signature sync, matching `Transcriber` in `app.api.deps`.

`_client_factory` is a module-level seam: tests monkeypatch it with a fake
client so nothing here ever opens a real network connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from amazon_transcribe.client import TranscribeStreamingClient

from app.config import settings
from app.voice import TranscriptionError
from app.voice.audio import to_pcm16

logger = logging.getLogger(__name__)

_CHUNK_BYTES = 8 * 1024


class _StreamingClient(Protocol):
    async def start_stream_transcription(self, **kwargs: Any) -> Any: ...


_client_factory: Any = TranscribeStreamingClient


async def _write_audio(input_stream: Any, pcm: bytes) -> None:
    for offset in range(0, len(pcm), _CHUNK_BYTES):
        chunk = pcm[offset : offset + _CHUNK_BYTES]
        await input_stream.send_audio_event(audio_chunk=chunk)
    await input_stream.end_stream()


async def _read_finals(output_stream: Any) -> list[str]:
    finals: list[str] = []
    async for event in output_stream:
        for result in event.transcript.results:
            if result.is_partial:
                continue
            if result.alternatives:
                finals.append(result.alternatives[0].transcript)
    return finals


async def _transcribe(pcm: bytes) -> str:
    try:
        client: _StreamingClient = _client_factory(region=settings.aws_region)
        stream = await client.start_stream_transcription(
            language_code=settings.transcribe_language_code,
            media_sample_rate_hz=settings.transcribe_sample_rate,
            media_encoding="pcm",
        )

        _, finals = await asyncio.gather(
            _write_audio(stream.input_stream, pcm),
            _read_finals(stream.output_stream),
        )
        return " ".join(finals).strip()
    except TranscriptionError:
        raise
    except Exception as exc:
        # Network, auth, or API errors from the SDK all surface identically
        # to callers — the detail is logged, never handed back to the client.
        logger.error("transcribe streaming failed: %s", exc)
        raise TranscriptionError("speech-to-text failed") from exc


def transcribe_audio(audio: bytes, content_type: str) -> str:
    """Decode `audio` and return the joined final transcript. Raises TranscriptionError."""
    return asyncio.run(_transcribe(to_pcm16(audio, content_type)))
