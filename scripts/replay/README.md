# Session replay

Replay canned rehearsal sessions against a running Airtight API — no browser, no
copy-paste. Useful for demoing the engine, watching a full session play out, or
re-running the same inputs repeatedly.

`../replay_session.py` is a **pure HTTP client**. It hits the same endpoints the
UI does (`POST /sessions`, `/answer`, `/clarify`) and never touches server code —
the scoring engine runs exactly as it does for a real user.

## Run

Bring the stack up, then run a scenario:

```sh
cd e2e && npm run stack:up          # or run the local dev servers
python3 scripts/replay_session.py scripts/replay/scenario-mixed.json
python3 scripts/replay_session.py --all
python3 scripts/replay_session.py --all --repeat 5      # each scenario 5x
python3 scripts/replay_session.py scripts/replay/scenario-mixed.json --report
```

Point at a non-default API with `--base-url` or `AIRTIGHT_API_URL`.

## Why scenarios are keyed by concern

The engine walks a **fixed agenda**, one owner per concern:

| # | concern | persona |
|---|---------|---------|
| 1 | technical_approach  | technical_evaluator |
| 2 | key_personnel       | technical_evaluator |
| 3 | transition          | technical_evaluator |
| 4 | risk                | technical_evaluator |
| 5 | compliance_security | contracting_officer |
| 6 | cost_realism        | contracting_officer |
| 7 | past_performance    | contracting_officer |
| 8 | operational_impact  | program_rep |

A scenario supplies one answer **per concern**; the runner feeds whichever answer
matches the concern the engine says is active. This is why it can't just be a flat
list of answers — the worked "sessions" in `docs/examples/example-sessions.md` are
curated *slices* of specific concern interactions, not contiguous runnable
sessions.

## Scenario format

```json
{
  "name": "Mixed realistic run",
  "notes": ["optional lines printed before the run"],
  "concerns": {
    "technical_approach": {
      "clarify": ["optional clarifying question asked (not scored) before answering"],
      "answer": "first-attempt presenter response (required)",
      "followup": "response used if the engine presses a same-concern follow-up"
    }
  }
}
```

- `answer` — required; the first scored response for that concern.
- `followup` — used when the engine returns a follow-up prompt on the same
  concern. Omit it and the runner resends `answer` (with a warning).
- `clarify` — optional list of clarifying questions; asked once, before the first
  answer, exercising the non-scored `/clarify` path.

The exact classification and meter for each turn are decided **live by the
engine** — a scenario shapes the inputs, not the outcome.
