"""Single choke point for Polly speech synthesis.

A new boto3 client is constructed per call, same as `BedrockClient` reads
AWS credentials lazily off the standard chain rather than at import time —
there's no per-request state worth pooling a client instance for here.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.voice import SynthesisError

logger = logging.getLogger(__name__)


def synthesize_speech(text: str, voice_id: str) -> bytes:
    """MP3 bytes for `text` in the persona's Polly voice. Raises SynthesisError."""
    try:
        client = boto3.client("polly", region_name=settings.aws_region)
        # boto3-stubs types VoiceId/Engine as Literals of the AWS-known values;
        # the persona content and settings supply plain strings, so the casts
        # trade that narrow checking for the module's actual (wider) contract.
        resp = client.synthesize_speech(
            Text=text,
            VoiceId=cast(Any, voice_id),
            OutputFormat="mp3",
            Engine=cast(Any, settings.polly_engine),
        )
        audio: bytes = resp["AudioStream"].read()
        return audio
    except (BotoCoreError, ClientError) as exc:
        logger.error("polly synthesize_speech failed: %s", exc)
        raise SynthesisError("speech synthesis failed") from exc
