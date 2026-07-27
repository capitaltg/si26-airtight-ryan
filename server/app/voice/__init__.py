"""Voice adapter package: audio transcoding, streaming transcription, and
speech synthesis. Every error the three modules raise is one of these three,
so callers (and eventually the endpoint layer) only need to catch `VoiceError`.
"""

from __future__ import annotations


class VoiceError(Exception):
    """Base class for the voice adapter's errors."""


class TranscriptionError(VoiceError):
    """Audio decode or speech-to-text failed."""


class SynthesisError(VoiceError):
    """Text-to-speech failed."""


__all__ = ["VoiceError", "TranscriptionError", "SynthesisError"]
