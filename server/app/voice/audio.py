"""Decodes any browser-recorded audio container to 16 kHz mono PCM16 via ffmpeg.

Shelling out (rather than a Python decoding library) means ffmpeg sniffs the
container from the bytes themselves — that's what makes Safari's MP4/AAC
input work with no special-casing, so `content_type` is only ever logged
here, never branched on. Nothing touches disk: the container comes in on
stdin and raw PCM comes out on stdout.
"""

from __future__ import annotations

import logging
import subprocess

from app.config import settings
from app.voice import TranscriptionError

logger = logging.getLogger(__name__)


def to_pcm16(audio: bytes, content_type: str) -> bytes:
    """Decode any browser container (webm/opus, mp4/aac, ogg) to 16 kHz mono s16le."""
    logger.info("decoding audio: content_type=%s bytes=%d", content_type, len(audio))
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                "pipe",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ac",
                "1",
                "-ar",
                str(settings.transcribe_sample_rate),
                "pipe:1",
            ],
            input=audio,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # ffmpeg missing from PATH or hung past the timeout — never surface
        # exc's details to the client, only that decoding failed.
        logger.error("ffmpeg invocation failed: %s", exc)
        raise TranscriptionError("audio decode failed") from exc

    if result.returncode != 0 or not result.stdout:
        # ffmpeg's stderr can contain fragments of the request path or other
        # server-side detail, so it is logged, never raised.
        logger.error(
            "ffmpeg decode failed (returncode=%s): %s",
            result.returncode,
            result.stderr.decode("utf-8", errors="replace"),
        )
        raise TranscriptionError("audio decode failed")

    return result.stdout
