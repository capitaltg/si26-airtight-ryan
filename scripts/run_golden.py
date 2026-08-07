#!/usr/bin/env python
"""Manual trigger for the live-Bedrock golden suite. Not part of the unit suite.

Runs from anywhere -- it resolves the server package off its own path:

    python scripts/run_golden.py

Extra arguments are passed straight through to pytest, so a single case is:

    python scripts/run_golden.py -k false_fact_ceiling

`pytest` on its own skips every golden case when the AWS credential chain
resolves nothing, which is what keeps offline CI green. That silent skip is the
failure mode this script exists to remove: it re-checks the same predicate the
suite gates on and exits non-zero *before* running, so "no credentials" can
never be mistaken for "the model is stable and valid".

This covers a manual or operator-triggered run only. It is not a substitute for
running the suite on a schedule in a protected environment -- nothing here
detects drift that lands while no one is watching.

Needs AWS credentials in the environment and Bedrock model access enabled for
BEDROCK_MODEL_ID in AWS_REGION. Costs real tokens: every case runs 3x.
"""

import subprocess
import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parents[1] / "server"

# pytest exits 5 when it collected nothing. For this suite that means the case
# file or the marker moved, not "all clear".
_EXIT_NO_TESTS_COLLECTED = 5


def main(argv: list[str]) -> int:
    # Importing the golden module pulls in the whole Anthropic SDK, which takes
    # several seconds cold (longer on Windows with a virus scanner reading
    # .venv). Say so before blocking, or a silent start reads as a hang and
    # invites the Ctrl+C that looks like an import crash.
    print("loading extraction stack (a few seconds)...", flush=True)

    # `app` is installed (pip install -e server) but `tests` is not packaged, so
    # the server directory has to be on the path before the golden module can be
    # read. Imported here rather than at module level to keep that ordering
    # requirement local instead of spreading it across two ruff configurations.
    sys.path.insert(0, str(_SERVER_DIR))
    from app.config import settings
    from tests.golden.test_golden import _CASES, _RUNS_PER_CASE, _bedrock_available

    if not _bedrock_available():
        print(
            "FAILED: no AWS credentials resolved; the golden suite would skip "
            "every case rather than measure it.",
            file=sys.stderr,
        )
        return 1

    print(
        f"model={settings.bedrock_model_id} region={settings.aws_region} "
        f"cases={len(_CASES)} runs_per_case={_RUNS_PER_CASE}"
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/golden", "-m", "golden", "-v", "-rs", *argv],
        cwd=_SERVER_DIR,
        check=False,
    )
    if completed.returncode == _EXIT_NO_TESTS_COLLECTED:
        print("FAILED: pytest collected no golden cases.", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
