# Task 4 Report: Persona-discriminator fixtures

## Status

Complete.

## Changes

- Added parametrized fixture checks for each custom persona's target concern.
- Replaced only Dana's technical-approach, Marcus's cost-realism, and Priya's operational-impact answers and follow-ups.
- Added identical-answer and non-guarantee notes to each custom fixture.
- Documented the fixture intent in the replay README.

## TDD Evidence

### RED

```bash
cd server && .venv/bin/pytest tests/test_replay_session.py -k discriminator -v
```

Result: 3 failed, 10 deselected. Each failure was the expected missing target phrase in the unchanged fixture answer.

### GREEN

```bash
cd server && .venv/bin/pytest tests/test_replay_session.py -v
```

Result: `13 passed in 0.02s`.

## Verification

```bash
cd server && .venv/bin/pytest tests/test_replay_session.py -v
python3 -m json.tool scripts/replay/scenario-custom-dana.json >/dev/null
python3 -m json.tool scripts/replay/scenario-custom-marcus.json >/dev/null
python3 -m json.tool scripts/replay/scenario-custom-priya.json >/dev/null
cd server && .venv/bin/ruff check tests/test_replay_session.py
git diff --check
```

- Replay tests: 13 passed.
- JSON validation: all three commands exited 0.
- Ruff: `All checks passed!`
- Diff check: no whitespace errors.

## Live Comparisons

Skipped. No API was listening on `localhost:8000`, and AWS credentials were not available in the environment. No external service was started.

## Self-review

- Each fixture still contains all eight fixed concern IDs and one matching custom persona.
- Target answers retain the required architecture, pricing, or operational context while withholding temporary-persona-specific proof.
- Notes and README state that baseline and customized runs receive identical answers, and that score differences are not guaranteed.
- No live scoring outcome is asserted.
- Preserved the pre-existing unrelated edit in `server/app/content/store/personas/technical_evaluator.md`.

## Files

- `scripts/replay/scenario-custom-dana.json`
- `scripts/replay/scenario-custom-marcus.json`
- `scripts/replay/scenario-custom-priya.json`
- `scripts/replay/README.md`
- `server/tests/test_replay_session.py`
- `AGENTS.md`
- `.superpowers/sdd/2026-08-02-persona-customization-replays/task-4-report.md`

## Concerns

- Live baseline comparisons remain unrun because prerequisites were unavailable.
