"""`transcribe_audio` is tested with both of its external dependencies faked:
`to_pcm16` (no real ffmpeg call) and the streaming client factory (no real
network/AWS credentials), per GLOBAL_CONSTRAINTS.md constraint 3.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.voice.transcribe as transcribe_module
from app.voice import TranscriptionError
from app.voice.transcribe import duration_seconds, transcribe_audio


def _result(transcript: str, *, is_partial: bool) -> SimpleNamespace:
    return SimpleNamespace(
        is_partial=is_partial,
        alternatives=[SimpleNamespace(transcript=transcript)],
    )


def _event(*results: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(transcript=SimpleNamespace(results=list(results)))


class _FakeInputStream:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.ended = False

    async def send_audio_event(self, audio_chunk: bytes) -> None:
        self.chunks.append(audio_chunk)

    async def end_stream(self) -> None:
        self.ended = True


class _FakeOutputStream:
    def __init__(self, events: list[SimpleNamespace]) -> None:
        self._events = events

    def __aiter__(self) -> _FakeOutputStream:
        self._iter = iter(self._events)
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeStream:
    def __init__(self, events: list[SimpleNamespace]) -> None:
        self.input_stream = _FakeInputStream()
        self.output_stream = _FakeOutputStream(events)


class _FakeStreamingClient:
    """Stands in for `TranscribeStreamingClient`."""

    last_instance: _FakeStreamingClient | None = None

    def __init__(self, region: str, events: list[SimpleNamespace] | None = None) -> None:
        self.region = region
        self.start_kwargs: dict[str, Any] | None = None
        self.last_stream: _FakeStream | None = None
        self._events = events if events is not None else []
        _FakeStreamingClient.last_instance = self

    async def start_stream_transcription(self, **kwargs: Any) -> _FakeStream:
        self.start_kwargs = kwargs
        self.last_stream = _FakeStream(self._events)
        return self.last_stream


def _events_two_partial_two_final() -> list[SimpleNamespace]:
    return [
        _event(_result("hello", is_partial=True)),
        _event(_result("hello there", is_partial=True)),
        _event(_result("hello there,", is_partial=False)),
        _event(_result("how are you", is_partial=False)),
    ]


def test_transcribe_audio_joins_only_final_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcribe_module, "to_pcm16", lambda audio, content_type: b"pcm-bytes")

    def factory(region: str) -> _FakeStreamingClient:
        return _FakeStreamingClient(region, events=_events_two_partial_two_final())

    monkeypatch.setattr(transcribe_module, "_client_factory", factory)

    result = transcribe_audio(b"raw-audio", "audio/webm")

    assert result.text == "hello there, how are you"
    assert result.duration_seconds == 0.0

    # The SDK call was wired up with the configured language/sample rate and a
    # fixed PCM encoding, and the input stream was properly closed — an
    # unclosed stream would hang a real AWS connection while this test stayed
    # green if nothing here asserted on it.
    client = _FakeStreamingClient.last_instance
    assert client is not None
    assert client.start_kwargs == {
        "language_code": transcribe_module.settings.transcribe_language_code,
        "media_sample_rate_hz": transcribe_module.settings.transcribe_sample_rate,
        "media_encoding": "pcm",
    }
    assert client.last_stream is not None
    assert client.last_stream.input_stream.ended is True


def test_transcribe_audio_wraps_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcribe_module, "to_pcm16", lambda audio, content_type: b"pcm-bytes")

    class _RaisingClient:
        def __init__(self, region: str) -> None:
            pass

        async def start_stream_transcription(self, **kwargs: Any) -> Any:
            raise RuntimeError("network exploded")

    monkeypatch.setattr(transcribe_module, "_client_factory", _RaisingClient)

    with pytest.raises(TranscriptionError):
        transcribe_audio(b"raw-audio", "audio/webm")


def test_duration_seconds_uses_pcm_frame_count() -> None:
    rate = 16_000
    assert duration_seconds(b"", rate) == 0
    assert duration_seconds(b"\0" * (rate * 2 * 120), rate) == 120
    assert duration_seconds(b"\0" * (rate * 2 * 120 + 2), rate) > 120
