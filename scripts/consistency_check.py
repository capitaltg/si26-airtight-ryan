#!/usr/bin/env python3
"""Run a replay scenario N times and prove the engine said the same thing every time.

This is the executable form of the consistency claim in
docs/ideation/2-scoring-and-drift.md: the same answer to the same prompt must
produce the same rows, the same delta, the same meter, and the same reply.

Two modes, testing two different things:

  default (cache on)
      Run 1 populates ``model_response_cache``; runs 2..N replay it. A pass
      means the request bytes hash identically across separate sessions, which
      is the guarantee app/bedrock/cache.py actually makes. A failure means
      something in the prompt drifted between runs — prompt text, ledger
      rendering, dict ordering — and the cache silently stopped hitting. It
      does NOT test the model; every call after run 1 is a replay.

  --no-cache
      Truncates ``model_response_cache`` between runs, so every run makes real
      Bedrock calls. This is the temperature-0 stability test from the docs:
      "run each exchange three times and confirm the extraction barely moves."
      A divergent turn is an unanchored case that wants an exemplar. Costs one
      full session of Sonnet calls per run.

Usage (stack must be up — `cd e2e && npm run stack:up`):

    python3 scripts/consistency_check.py scripts/replay/scenario-contradiction.json
    python3 scripts/consistency_check.py --all --runs 3
    python3 scripts/consistency_check.py scripts/replay/scenario-false-fact.json --no-cache
    python3 scripts/consistency_check.py --all --expect-row contradiction

Exit code is 0 only if every run of every scenario agreed and every expected
rubric row actually fired.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

from replay_session import DEFAULT_BASE_URL, FIXTURE_DIR, _get, c, replay

# Truncating the cache table is what forces fresh Bedrock calls. Overridable
# with --reset-cmd for a stack that isn't the compose one (a local Postgres, a
# different container name, psql on the host).
DEFAULT_RESET_CMD = (
    'docker compose exec -T postgres psql -U airtight -d airtight '
    '-c "TRUNCATE model_response_cache"'
)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Fields compared turn by turn. `prompt` and `reply` are the model's own words;
# the rest is the engine's arithmetic. Both have to hold for a run to count as
# reproducible, since the user sees both.
COMPARED = (
    "kind",
    "persona_id",
    "concern_id",
    "is_follow_up",
    "prompt",
    "sent",
    "matched_rows",
    "support_delta",
    "meter",
    "capped",
    "concern_status",
    "reply",
    "rationale",
    "remaining",
)


def _abbrev(value: object, width: int = 110) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def diff_runs(base: dict, other: dict) -> list[str]:
    """Human-readable differences between two runs of the same scenario.

    Empty list means the runs are identical on every compared field. Turn count
    is checked first: if the runs took different paths through the agenda
    (a follow-up fired in one and not the other) that is the finding, and a
    field-by-field diff past that point would just be noise.
    """
    diffs: list[str] = []
    base_turns, other_turns = base["turns"], other["turns"]

    if len(base_turns) != len(other_turns):
        diffs.append(f"turn count: {len(base_turns)} vs {len(other_turns)}")

    for i, (b, o) in enumerate(zip(base_turns, other_turns), start=1):
        for field in COMPARED:
            if b.get(field) != o.get(field):
                diffs.append(
                    f"turn {i} ({b['concern_id']}) {field}:\n"
                    f"      run 1: {_abbrev(b.get(field))}\n"
                    f"      this:  {_abbrev(o.get(field))}"
                )

    if base["final_meters"] != other["final_meters"]:
        diffs.append(
            f"final meters:\n"
            f"      run 1: {_abbrev(base['final_meters'])}\n"
            f"      this:  {_abbrev(other['final_meters'])}"
        )
    if base["concern_status"] != other["concern_status"]:
        diffs.append(
            f"concern statuses:\n"
            f"      run 1: {_abbrev(base['concern_status'])}\n"
            f"      this:  {_abbrev(other['concern_status'])}"
        )
    return diffs


def rows_fired(run: dict) -> set[str]:
    """Every rubric row that matched anywhere in the run."""
    return {row for turn in run["turns"] for row in turn.get("matched_rows", [])}


def missing_rows(run: dict, expected: list[str]) -> list[str]:
    """Expected rows that never fired.

    A scenario that quietly stops exercising the behaviour it was written for
    would otherwise pass as 'consistent' while testing nothing, so this is a
    failure, not a warning.
    """
    fired = rows_fired(run)
    return [row for row in expected if row not in fired]


def reset_cache(cmd: str) -> None:
    proc = subprocess.run(
        cmd, shell=True, cwd=REPO_ROOT, capture_output=True, text=True
    )
    if proc.returncode != 0:
        sys.exit(
            f"cache reset failed (exit {proc.returncode}): {cmd}\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )


def check_scenario(
    base_url: str,
    scenario: dict,
    *,
    runs: int,
    quiet: bool,
    reset_cmd: str | None,
    expect_rows: list[str],
) -> bool:
    """Replay one scenario `runs` times and report. True if it held."""
    name = scenario.get("name", "(unnamed)")
    expected = list(dict.fromkeys(list(scenario.get("expect_rows", [])) + expect_rows))

    results: list[dict] = []
    for n in range(1, runs + 1):
        if reset_cmd is not None and n > 1:
            print(c(f"\n  [run {n}] truncating model_response_cache", "2"))
            reset_cache(reset_cmd)
        print(c(f"\n----- {name}: run {n} of {runs} -----", "1;34"))
        results.append(replay(base_url, scenario, quiet, False))

    print(c(f"\n=== consistency: {name} ===", "1;35"))
    ok = True

    base = results[0]
    for n, other in enumerate(results[1:], start=2):
        diffs = diff_runs(base, other)
        if diffs:
            ok = False
            print(c(f"  run {n}: DIVERGED from run 1 ({len(diffs)} difference(s))", "31"))
            for d in diffs:
                print(f"    - {d}")
        else:
            print(c(f"  run {n}: identical to run 1", "32"))

    fired = sorted(rows_fired(base))
    print(c(f"  rows fired: {', '.join(fired) or '(none)'}", "2"))
    absent = missing_rows(base, expected)
    if absent:
        ok = False
        print(
            c(
                f"  EXPECTED ROWS NEVER FIRED: {', '.join(absent)} — the scenario "
                "stopped exercising what it was written for",
                "31",
            )
        )
    elif expected:
        print(c(f"  expected rows present: {', '.join(expected)}", "32"))

    return ok


def _resolve(args: argparse.Namespace) -> list[str]:
    if args.all:
        return sorted(glob.glob(os.path.join(FIXTURE_DIR, "scenario-*.json")))
    if not args.scenarios:
        sys.exit("nothing to run: pass a scenario path or --all")
    return args.scenarios


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("scenarios", nargs="*", help="scenario JSON path(s)")
    ap.add_argument("--all", action="store_true", help=f"every scenario-*.json in {FIXTURE_DIR}")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base (default {DEFAULT_BASE_URL})")
    ap.add_argument("--runs", type=int, default=2, help="runs per scenario (default 2)")
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="truncate the response cache between runs so every run hits Bedrock (costs money)",
    )
    ap.add_argument("--reset-cmd", default=DEFAULT_RESET_CMD, help="command used by --no-cache")
    ap.add_argument(
        "--expect-row",
        action="append",
        default=[],
        metavar="ROW",
        help="fail unless this rubric row fires somewhere in the run (repeatable)",
    )
    ap.add_argument("--quiet", action="store_true", help="skip the per-turn play-by-play")
    args = ap.parse_args()

    if args.runs < 2:
        sys.exit("--runs must be at least 2; comparing one run to itself proves nothing")

    try:
        _get(args.base_url, "/health")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"API not reachable at {args.base_url} ({exc}). Is the stack up?")

    reset_cmd = args.reset_cmd if args.no_cache else None
    if reset_cmd:
        print(
            c(
                f"--no-cache: every one of the {args.runs} runs makes real Bedrock calls.",
                "33",
            )
        )

    failed: list[str] = []
    for path in _resolve(args):
        with open(path) as f:
            scenario = json.load(f)
        ok = check_scenario(
            args.base_url,
            scenario,
            runs=args.runs,
            quiet=args.quiet,
            reset_cmd=reset_cmd,
            expect_rows=args.expect_row,
        )
        if not ok:
            failed.append(scenario.get("name", os.path.basename(path)))

    print()
    if failed:
        print(c(f"FAIL: {len(failed)} scenario(s) inconsistent: {', '.join(failed)}", "1;31"))
        return 1
    print(c("PASS: every scenario reproduced identically", "1;32"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
