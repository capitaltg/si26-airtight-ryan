"""Voice HTTP surface: recording upload (`/answer_audio`) and replay
(`/turns/{i}/audio`). The core assertion across this file is equivalence —
the voice path must score byte-identically to the text path, proving tasks
1-4 only added a new front door onto the untouched orchestrator/scoring core.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_synthesizer, get_transcriber
from app.voice import SynthesisError, TranscriptionError
from tests.test_api import client  # noqa: F401  (reused fixture)

# Fields shared by AnswerResponse and VoiceAnswerResponse; the equivalence test
# below asserts these match exactly between the text and voice paths.
_SHARED_ANSWER_FIELDS = [
    "support_delta",
    "matched_rows",
    "meter",
    "capped",
    "concern_status",
    "reply",
    "rationale",
    "next_prompt",
]


def _fake_transcribe(transcript: str):
    def _transcribe(audio: bytes, content_type: str) -> str:
        return transcript

    return _transcribe


def _raising_transcribe(exc: Exception):
    def _transcribe(audio: bytes, content_type: str) -> str:
        raise exc

    return _transcribe


def _fake_synthesize(audio_bytes: bytes = b"fake-mp3-bytes"):
    def _synthesize(text: str, voice_id: str) -> bytes:
        return audio_bytes

    return _synthesize


def _raising_synthesize(exc: Exception):
    def _synthesize(text: str, voice_id: str) -> bytes:
        raise exc

    return _synthesize


@pytest.fixture
def voice_client(client: TestClient) -> Iterator[TestClient]:  # noqa: F811
    """The shared `client` fixture plus default (successful) voice fakes.
    Individual tests override `get_transcriber` / `get_synthesizer` further
    for failure scenarios."""
    client.app.dependency_overrides[get_transcriber] = lambda: _fake_transcribe(
        "Here is the architecture."
    )
    client.app.dependency_overrides[get_synthesizer] = lambda: _fake_synthesize()
    yield client


def test_answer_audio_scores_identically_to_text_answer(voice_client: TestClient) -> None:
    transcript = "Here is the architecture."
    voice_client.app.dependency_overrides[get_transcriber] = lambda: _fake_transcribe(transcript)

    session_a = voice_client.post("/sessions").json()["id"]
    session_b = voice_client.post("/sessions").json()["id"]

    text_resp = voice_client.post(f"/sessions/{session_a}/answer", json={"answer": transcript})
    assert text_resp.status_code == 200
    text_body = text_resp.json()

    voice_resp = voice_client.post(
        f"/sessions/{session_b}/answer_audio",
        files={"audio": ("recording.webm", b"\x00\x01\x02fake-audio-bytes", "audio/webm")},
    )
    assert voice_resp.status_code == 200
    voice_body = voice_resp.json()

    for field in _SHARED_ANSWER_FIELDS:
        assert voice_body[field] == text_body[field], f"field {field!r} diverged"

    # Voice-only fields ride alongside the shared contract.
    assert voice_body["transcript"] == transcript
    assert voice_body["reply_audio"] is not None
    assert voice_body["next_prompt_audio"] is not None


def test_failed_transcription_returns_422_and_leaves_session_untouched(
    voice_client: TestClient,
) -> None:
    session_id = voice_client.post("/sessions").json()["id"]
    before = voice_client.get(f"/sessions/{session_id}").json()

    voice_client.app.dependency_overrides[get_transcriber] = lambda: _raising_transcribe(
        TranscriptionError("boom")
    )
    r = voice_client.post(
        f"/sessions/{session_id}/answer_audio",
        files={"audio": ("recording.webm", b"whatever", "audio/webm")},
    )
    assert r.status_code == 422

    after = voice_client.get(f"/sessions/{session_id}").json()
    assert after["meters"] == before["meters"]
    assert all(m["support"] == 50 for m in after["meters"])
    assert after["prompt"]["concern_id"] == before["prompt"]["concern_id"]


def test_blank_transcript_returns_422_and_leaves_session_untouched(
    voice_client: TestClient,
) -> None:
    session_id = voice_client.post("/sessions").json()["id"]
    before = voice_client.get(f"/sessions/{session_id}").json()

    voice_client.app.dependency_overrides[get_transcriber] = lambda: _fake_transcribe("   ")
    r = voice_client.post(
        f"/sessions/{session_id}/answer_audio",
        files={"audio": ("recording.webm", b"whatever", "audio/webm")},
    )
    assert r.status_code == 422

    after = voice_client.get(f"/sessions/{session_id}").json()
    assert after["meters"] == before["meters"]
    assert all(m["support"] == 50 for m in after["meters"])
    assert after["prompt"]["concern_id"] == before["prompt"]["concern_id"]


def test_failed_synthesis_still_scores_turn_with_null_audio(voice_client: TestClient) -> None:
    session_id = voice_client.post("/sessions").json()["id"]

    voice_client.app.dependency_overrides[get_synthesizer] = lambda: _raising_synthesize(
        SynthesisError("polly down")
    )
    r = voice_client.post(
        f"/sessions/{session_id}/answer_audio",
        files={"audio": ("recording.webm", b"whatever", "audio/webm")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply_audio"] is None
    assert body["next_prompt_audio"] is None
    assert body["meter"] == 52
    assert body["capped"] is False


def test_answer_audio_persists_and_replays(voice_client: TestClient) -> None:
    session_id = voice_client.post("/sessions").json()["id"]
    audio_bytes = b"\x00\x01\x02fake-audio-bytes"

    r = voice_client.post(
        f"/sessions/{session_id}/answer_audio",
        files={"audio": ("recording.webm", audio_bytes, "audio/webm")},
    )
    assert r.status_code == 200

    replay = voice_client.get(f"/sessions/{session_id}/turns/0/audio")
    assert replay.status_code == 200
    assert replay.content == audio_bytes
    assert replay.headers["content-type"] == "audio/webm"


def test_replay_404s_for_turn_with_no_audio(voice_client: TestClient) -> None:
    session_id = voice_client.post("/sessions").json()["id"]
    r = voice_client.post(
        f"/sessions/{session_id}/answer", json={"answer": "Here is the architecture."}
    )
    assert r.status_code == 200

    replay = voice_client.get(f"/sessions/{session_id}/turns/0/audio")
    assert replay.status_code == 404


def test_next_prompt_audio_is_null_on_final_concern(voice_client: TestClient) -> None:
    session_id = voice_client.post("/sessions").json()["id"]

    # Drive the session to its last concern, mirroring test_api.py's pattern.
    body = None
    for _ in range(20):
        state = voice_client.get(f"/sessions/{session_id}").json()
        if state["done"]:
            break
        body = voice_client.post(
            f"/sessions/{session_id}/answer_audio",
            files={"audio": ("recording.webm", b"fake-audio-bytes", "audio/webm")},
        ).json()

    assert body is not None
    assert body["done"] is True
    assert body["next_prompt_audio"] is None
