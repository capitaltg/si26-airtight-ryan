"""Polly is mocked at `boto3.client` — the module under test never opens a
real AWS connection, per GLOBAL_CONSTRAINTS.md constraint 3.
"""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.config import settings
from app.voice import SynthesisError
from app.voice.polly import synthesize_speech


class _FakeAudioStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakePollyClient:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def synthesize_speech(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def test_synthesize_speech_returns_audio_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakePollyClient(response={"AudioStream": _FakeAudioStream(b"mp3-bytes")})
    monkeypatch.setattr(
        "app.voice.polly.boto3.client", lambda service, region_name: fake_client
    )

    result = synthesize_speech("Hello there.", "Joanna")

    assert result == b"mp3-bytes"
    assert len(fake_client.calls) == 1
    kwargs = fake_client.calls[0]
    assert kwargs["VoiceId"] == "Joanna"
    assert kwargs["Engine"] == settings.polly_engine
    assert kwargs["OutputFormat"] == "mp3"
    assert kwargs["Text"] == "Hello there."


def test_synthesize_speech_wraps_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
        "SynthesizeSpeech",
    )
    fake_client = _FakePollyClient(error=error)
    monkeypatch.setattr(
        "app.voice.polly.boto3.client", lambda service, region_name: fake_client
    )

    with pytest.raises(SynthesisError):
        synthesize_speech("Hello there.", "Joanna")
