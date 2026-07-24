#!/usr/bin/env python3
"""Replay an authored scenario against a running Airtight API.

Drives the same REST endpoints the UI uses (POST /sessions, /answer, /clarify),
feeding canned presenter answers from a scenario file instead of by hand. No
browser, no copy-paste. Prints a play-by-play: each persona prompt, the answer
fed, the resulting classification, and the meter.

This is a pure HTTP client. It does NOT touch or change the scoring engine — it
only sends the same requests the frontend sends.

Scenario format (see scripts/replay/scenario-mixed.json)
--------------------------------------------------------
The engine walks a FIXED agenda of concerns, one owner each:
  technical_approach, key_personnel, transition, risk (technical_evaluator)
  compliance_security, cost_realism, past_performance (contracting_officer)
  operational_impact (program_rep)

So a scenario keys its answers BY concern_id, and the runner feeds whichever
answer matches the concern the engine says is active. Each concern entry has:
  answer    - the first-attempt presenter response (required)
  followup  - response used if the engine presses a same-concern follow-up
  clarify   - optional list of clarifying questions asked (not scored) before
              the first answer, to exercise the /clarify path

Usage (stack must be up — `cd e2e && npm run stack:up`, or local dev servers):

    python3 scripts/replay_session.py scripts/replay/scenario-mixed.json
    python3 scripts/replay_session.py --all
    python3 scripts/replay_session.py --all --repeat 5     # run each 5x
    python3 scripts/replay_session.py scripts/replay/scenario-mixed.json --report
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_BASE_URL = os.environ.get("AIRTIGHT_API_URL", "http://localhost:8000")
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "replay")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "reports")

# A hard stop so a misconfigured scenario can never spin forever. The engine
# caps every concern at 2 attempts across at most 8 concerns, so a complete run
# is well under this.
MAX_TURNS = 40

_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def _post(base_url: str, path: str, body: dict | None) -> dict:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{exc.code} {path}: {detail}") from exc


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base_url}{path}", timeout=120) as resp:
        return json.loads(resp.read())


def _fmt_prompt(prompt: dict) -> str:
    tag = c(" [follow-up]", "33") if prompt["is_follow_up"] else ""
    who = c(f"{prompt['persona_id']}/{prompt['concern_id']}", "36")
    return f"{who}{tag}\n    {prompt['prompt']}"


def _fmt_result(r: dict) -> str:
    rows = ", ".join(r["matched_rows"]) or "(none)"
    delta = r["support_delta"]
    delta_s = c(f"{delta:+d}", "32" if delta > 0 else "31" if delta < 0 else "2")
    cap = c(" CAPPED", "31") if r["capped"] else ""
    status_color = {"satisfied": "32", "dodged": "31", "partial": "33"}.get(
        r["concern_status"], "0"
    )
    return (
        f"    -> rows=[{rows}] delta={delta_s} "
        f"meter={c(str(r['meter']), '1')}{cap} status={c(r['concern_status'], status_color)}"
    )


def _answer_for(spec: dict, is_follow_up: bool, cid: str) -> str:
    if is_follow_up:
        if spec.get("followup"):
            return spec["followup"]
        print(c(f"    ! follow-up on {cid} but scenario has no `followup`; resending `answer`", "33"))
    return spec["answer"]


def replay(base_url: str, scenario: dict, quiet: bool, want_report: bool) -> dict:
    """Run one scenario end to end. Returns final meters keyed by persona."""
    name = scenario.get("name", "(unnamed)")
    concerns = scenario["concerns"]
    print(c(f"\n=== {name} ===", "1;35"))
    for note in scenario.get("notes", []):
        print(c(f"  note: {note}", "33"))

    state = _post(base_url, "/sessions", None)
    session_id = state["id"]
    prompt = state["prompt"]
    clarified: set[str] = set()  # concerns whose clarifications were already asked

    for _ in range(MAX_TURNS):
        if prompt is None:
            break
        cid = prompt["concern_id"]
        is_follow_up = prompt["is_follow_up"]
        spec = concerns.get(cid)

        if not quiet:
            print(f"\n  {_fmt_prompt(prompt)}")

        if spec is None:
            print(c(f"    ! scenario has no entry for `{cid}`; sending a neutral answer to advance", "31"))
            res = _post(base_url, f"/sessions/{session_id}/answer", {"answer": "No further detail at this time."})
            prompt = res["next_prompt"]
            if res["done"]:
                break
            continue

        # Clarifications, if any, are asked once, before the first scored answer.
        if not is_follow_up and cid not in clarified:
            for q in spec.get("clarify", []):
                if not quiet:
                    print(c(f"    ? clarify: {q}", "34"))
                try:
                    res = _post(base_url, f"/sessions/{session_id}/clarify", {"question": q})
                except RuntimeError as exc:
                    print(c(f"    ! clarify rejected: {exc}", "31"))
                    break
                if not quiet:
                    print(f"    <- {res['reply']}")
                    print(c(f"    (clarifications remaining: {res['remaining']})", "2"))
                prompt = res["prompt"]  # active prompt is unchanged
            clarified.add(cid)

        text = _answer_for(spec, is_follow_up, cid)
        if not quiet:
            print(f"    > answer: {text}")
        res = _post(base_url, f"/sessions/{session_id}/answer", {"answer": text})
        if not quiet:
            print(_fmt_result(res))
            print(f"    <- {res['reply']}")
        prompt = res["next_prompt"]
        if res["done"]:
            break
    else:
        print(c(f"  ! hit MAX_TURNS ({MAX_TURNS}) without completing", "31"))

    _post(base_url, f"/sessions/{session_id}/end", None)
    final_state = _get(base_url, f"/sessions/{session_id}")
    final = {m["persona_id"]: (m["support"], m["capped"]) for m in final_state["meters"]}
    meters_s = "  ".join(
        f"{p}={c(str(s), '1')}{c('(capped)', '31') if cap else ''}"
        for p, (s, cap) in final.items()
    )
    print(c(f"\n  final meters: {meters_s}", "1"))
    print(c(f"  concern statuses: {json.dumps(final_state['concern_status'])}", "2"))

    if want_report:
        report = _get(base_url, f"/sessions/{session_id}/report")
        print(c("\n  --- report ---", "2"))
        print("  " + json.dumps(report, indent=2).replace("\n", "\n  "))
        path = _save_report(name, session_id, report)
        print(c(f"  report saved: {path}", "2"))

    return final


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "session"


def _save_report(name: str, session_id: str, report: dict) -> str:
    """Write the after-action report to docs/reports and return its path."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = f"{stamp}-{_slug(name)}-{session_id}.json"
    path = os.path.join(REPORT_DIR, fname)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return os.path.relpath(path)


def _resolve(args: argparse.Namespace) -> list[str]:
    if args.all:
        return sorted(glob.glob(os.path.join(FIXTURE_DIR, "scenario-*.json")))
    if not args.scenarios:
        sys.exit("nothing to run: pass a scenario path or --all")
    return args.scenarios


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenarios", nargs="*", help="scenario JSON path(s)")
    ap.add_argument("--all", action="store_true", help=f"run every scenario-*.json in {FIXTURE_DIR}")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base (default {DEFAULT_BASE_URL})")
    ap.add_argument("--repeat", type=int, default=1, help="run each scenario N times")
    ap.add_argument("--report", action="store_true", help="fetch the after-action report and save it to docs/reports/")
    ap.add_argument("--quiet", action="store_true", help="only session name and final meters")
    args = ap.parse_args()

    try:
        _get(args.base_url, "/health")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"API not reachable at {args.base_url} ({exc}). Is the stack up?")

    for _ in range(args.repeat):
        for path in _resolve(args):
            with open(path) as f:
                scenario = json.load(f)
            replay(args.base_url, scenario, args.quiet, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
