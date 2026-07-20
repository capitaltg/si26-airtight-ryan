#!/usr/bin/env python
"""Manual check that real Bedrock access works. Not part of the test suite.

Run from the server package so `app` is importable:

    cd server && .venv/bin/python ../scripts/smoke_bedrock.py

Needs AWS credentials in the environment and Bedrock model access enabled for
BEDROCK_MODEL_ID in AWS_REGION. Exits non-zero on failure.
"""

import sys

from app.bedrock.client import BedrockClient
from app.config import settings


def main() -> int:
    print(f"model={settings.bedrock_model_id} region={settings.aws_region}")
    try:
        reply = BedrockClient().react("Say READY.")
    except Exception as exc:  # noqa: BLE001 - surface whatever the AWS chain raises
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"reply: {reply}")
    return 0 if "READY" in reply.upper() else 1


if __name__ == "__main__":
    raise SystemExit(main())
