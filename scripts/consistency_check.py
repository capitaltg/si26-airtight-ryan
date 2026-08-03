#!/usr/bin/env python3
"""Run a replay scenario N times and prove the engine said the same thing every time.

This is the executable form of the consistency claim in
docs/ideation/2-scoring-and-drift.md: the same answer to the same prompt must
produce the same rows, the same delta, the same meter, and the same reply.

Two repeat-run modes test different things; `--compare-baseline` compares
default-persona and customized runs as an observation:

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
    python3 scripts/consistency_check.py scripts/replay/scenario-custom-dana.json --compare-baseline
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from replay_session import (
    DEFAULT_BASE_URL,
    FIXTURE_DIR,
    _format_rows,
    _get,
    c,
    replay,
    replay_with_personas,
)

# Truncating the cache table is what forces fresh Bedrock calls. Overridable
# with --reset-cmd for a stack that isn't the compose one (a local Postgres, a
# different container name, psql on the host).
DEFAULT_RESET_CMD = (
    'docker compose exec -T postgres psql -U airtight -d airtight '
    '-c "TRUNCATE model_response_cache"'
)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT_DIR = Path(REPO_ROOT) / "docs" / "reports"

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
    "row_counts",
    "support_delta",
    "raw_support_delta",
    "meter",
    "capped",
    "concern_status",
    "reply",
    "rationale",
    "remaining",
)
SCORE_FIELDS = (
    "matched_rows",
    "row_counts",
    "support_delta",
    "raw_support_delta",
    "meter",
    "capped",
    "concern_status",
)


def _abbrev(value: object, width: int = 110) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _difference_records(base: dict, other: dict) -> list[dict[str, Any]]:
    """Complete, structured differences between two runs of one scenario."""
    differences: list[dict[str, Any]] = []
    base_turns, other_turns = base["turns"], other["turns"]

    if len(base_turns) != len(other_turns):
        differences.append(
            {
                "scope": "session",
                "field": "turn_count",
                "run_1": len(base_turns),
                "this": len(other_turns),
            }
        )

    for i, (b, o) in enumerate(zip(base_turns, other_turns), start=1):
        for field in COMPARED:
            if b.get(field) != o.get(field):
                differences.append(
                    {
                        "scope": "turn",
                        "turn": i,
                        "concern_id": b.get("concern_id"),
                        "field": field,
                        "run_1": b.get(field),
                        "this": o.get(field),
                    }
                )

    if base["final_meters"] != other["final_meters"]:
        differences.append(
            {
                "scope": "session",
                "field": "final_meters",
                "run_1": base["final_meters"],
                "this": other["final_meters"],
            }
        )
    if base["concern_status"] != other["concern_status"]:
        differences.append(
            {
                "scope": "session",
                "field": "concern_status",
                "run_1": base["concern_status"],
                "this": other["concern_status"],
            }
        )
    return differences


def diff_runs(base: dict, other: dict) -> list[str]:
    """Human-readable, abbreviated differences between two scenario runs."""
    diffs: list[str] = []
    for difference in _difference_records(base, other):
        field = difference["field"]
        if difference["scope"] == "turn":
            diffs.append(
                f"turn {difference['turn']} ({difference['concern_id']}) {field}:\n"
                f"      run 1: {_abbrev(difference['run_1'])}\n"
                f"      this:  {_abbrev(difference['this'])}"
            )
            continue
        label = field.replace("_", " ")
        diffs.append(
            f"{label}:\n"
            f"      run 1: {_abbrev(difference['run_1'])}\n"
            f"      this:  {_abbrev(difference['this'])}"
        )
    return diffs


def _score_summary(run: dict[str, Any]) -> str:
    """Compact score signature for one replayed session."""
    turns = []
    for turn in run["turns"]:
        if turn.get("kind") != "answer":
            continue
        rows = _format_rows(turn.get("matched_rows", []), turn.get("row_counts"))
        raw = turn.get("raw_support_delta", turn["support_delta"])
        clamp = f" (clamped from {raw:+d})" if abs(raw) > 2 else ""
        turns.append(
            f"{turn['concern_id']} rows={rows} delta={turn['support_delta']:+d}{clamp} "
            f"meter={turn['meter']} capped={turn['capped']}"
        )
    scored = " | ".join(turns) or "(no scored turns)"
    return f"{scored}; final_meters={_abbrev(run['final_meters'])}"


def _score_differences(base: dict[str, Any], other: dict[str, Any]) -> list[str]:
    """Names of score-bearing fields that changed between two runs."""
    changed: list[str] = []
    if len(base["turns"]) != len(other["turns"]):
        changed.append("turn count")

    for b, o in zip(base["turns"], other["turns"]):
        for field in SCORE_FIELDS:
            if b.get(field) != o.get(field) and field not in changed:
                changed.append(field)

    if base["final_meters"] != other["final_meters"]:
        changed.append("final meters")
    return changed


def consistency_report(
    name: str,
    results: list[dict[str, Any]],
    *,
    expected_rows: list[str] | None = None,
    missing_expected_rows: list[str] | None = None,
    passed: bool = True,
    scenario_path: str | None = None,
) -> dict[str, Any]:
    """Machine-readable score and divergence details for one scenario."""
    runs = []
    for run_number, result in enumerate(results, start=1):
        score_turns = []
        for turn_number, turn in enumerate(result["turns"], start=1):
            if turn.get("kind") != "answer":
                continue
            score_turns.append(
                {
                    "turn": turn_number,
                    "concern_id": turn["concern_id"],
                    "matched_rows": turn.get("matched_rows", []),
                    "row_counts": turn.get("row_counts", {}),
                    "support_delta": turn["support_delta"],
                    "raw_support_delta": turn.get("raw_support_delta", turn["support_delta"]),
                    "meter": turn["meter"],
                    "capped": turn["capped"],
                    "concern_status": turn["concern_status"],
                }
            )
        runs.append(
            {
                "run": run_number,
                "score_turns": score_turns,
                "final_meters": result["final_meters"],
            }
        )

    base = results[0]
    comparisons = [
        {
            "run": run_number,
            "differences": _difference_records(base, other),
            "score_differences": _score_differences(base, other),
        }
        for run_number, other in enumerate(results[1:], start=2)
    ]
    return {
        "name": name,
        "scenario_path": scenario_path,
        "passed": passed,
        "expected_rows": expected_rows or [],
        "missing_expected_rows": missing_expected_rows or [],
        "runs": runs,
        "comparisons": comparisons,
    }


def write_report(report: dict[str, Any], *, report_dir: Path = REPORT_DIR) -> Path:
    """Save one consistency-check report and return its path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = report_dir / f"{stamp}-consistency-report.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


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
    report_scenarios: list[dict[str, Any]] | None = None,
    scenario_path: str | None = None,
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
    print(c("  score summary:", "2"))
    for n, result in enumerate(results, start=1):
        print(f"    run {n}: {_score_summary(result)}")

    ok = True

    base = results[0]
    for n, other in enumerate(results[1:], start=2):
        diffs = diff_runs(base, other)
        if diffs:
            ok = False
            print(c(f"  run {n}: DIVERGED from run 1 ({len(diffs)} difference(s))", "31"))
            score_diffs = _score_differences(base, other)
            if score_diffs:
                print(c(f"    SCORE DIVERGED: {', '.join(score_diffs)}", "31"))
            else:
                print(c("    scores matched; non-score output diverged", "33"))
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

    if report_scenarios is not None:
        report_scenarios.append(
            consistency_report(
                name,
                results,
                expected_rows=expected,
                missing_expected_rows=absent,
                passed=ok,
                scenario_path=scenario_path,
            )
        )

    return ok


def compare_baseline(
    base_url: str,
    scenario: dict,
    quiet: bool,
    report_scenarios: list[dict[str, Any]] | None = None,
    scenario_path: str | None = None,
) -> bool:
    """Report how a temporary persona customization changes one replay."""
    baseline_scenario = {
        key: value for key, value in scenario.items() if key != "personas"
    }
    baseline = replay(base_url, baseline_scenario, quiet, False)
    customized = replay_with_personas(base_url, scenario, quiet, False)
    diffs = diff_runs(baseline, customized)
    score_diffs = _score_differences(baseline, customized)

    print(c(f"\n=== baseline comparison: {scenario.get('name', '(unnamed)')} ===", "1;35"))
    print(c(f"  baseline score: {_score_summary(baseline)}", "2"))
    print(c(f"  customized score: {_score_summary(customized)}", "2"))
    if not diffs:
        print(c("  no scoring or reaction differences", "2"))
    elif score_diffs:
        print(c(f"  SCORE CHANGED: {', '.join(score_diffs)}", "33"))
    else:
        print(c("  score unchanged; reaction changed", "33"))
    for diff in diffs:
        print(f"    - {diff}")

    if report_scenarios is not None:
        report = consistency_report(
            scenario.get("name", "(unnamed)"),
            [baseline, customized],
            passed=True,
            scenario_path=scenario_path,
        )
        report["comparison_mode"] = "baseline"
        report_scenarios.append(report)
    return True


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
    ap.add_argument(
        "--compare-baseline",
        action="store_true",
        help="compare each customized scenario with its default-persona baseline",
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
    ap.add_argument("--report", action="store_true", help="save score and divergence details to docs/reports/")
    args = ap.parse_args()

    if args.runs < 2:
        sys.exit("--runs must be at least 2; comparing one run to itself proves nothing")
    if args.compare_baseline and args.runs != 2:
        sys.exit("--compare-baseline always runs one baseline/customized pair; omit --runs")
    if args.compare_baseline and args.no_cache:
        sys.exit("--compare-baseline does not support --no-cache")

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
    report_scenarios: list[dict[str, Any]] | None = [] if args.report else None
    scenario_paths = [str(Path(path).resolve()) for path in _resolve(args)]
    for path in scenario_paths:
        with open(path) as f:
            scenario = json.load(f)
        if args.compare_baseline:
            if not isinstance(scenario.get("personas"), dict):
                sys.exit("--compare-baseline requires personas as an object")
            ok = compare_baseline(
                args.base_url,
                scenario,
                args.quiet,
                report_scenarios,
                path,
            )
        else:
            ok = check_scenario(
                args.base_url,
                scenario,
                runs=args.runs,
                quiet=args.quiet,
                reset_cmd=reset_cmd,
                expect_rows=args.expect_row,
                report_scenarios=report_scenarios,
                scenario_path=path,
            )
        if not ok:
            failed.append(scenario.get("name", os.path.basename(path)))

    print()
    if report_scenarios is not None:
        path = write_report(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "invocation": {
                    "base_url": args.base_url,
                    "runs": args.runs,
                    "no_cache": args.no_cache,
                    "compare_baseline": args.compare_baseline,
                    "reset_cmd": reset_cmd,
                    "expect_rows": args.expect_row,
                    "scenarios": scenario_paths,
                },
                "scenarios": report_scenarios,
                "passed": not failed,
            }
        )
        try:
            display_path = path.relative_to(REPO_ROOT)
        except ValueError:
            display_path = path
        print(c(f"report saved: {display_path}", "2"))

    if failed:
        print(c(f"FAIL: {len(failed)} scenario(s) inconsistent: {', '.join(failed)}", "1;31"))
        return 1
    print(c("PASS: every scenario reproduced identically", "1;32"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
