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

## Fix Round: Adaptive Baseline Alignment

### Changes

- Kept generic repeat-run comparison positional and unchanged.
- Added baseline-only comparison keyed by concern and attempt (`initial`,
  `follow-up`, or clarification), with added and removed turns reported
  explicitly.
- Updated baseline reports to use aligned differences and aligned
  score-bearing fields.
- Added one-sided-follow-up regression coverage and forbidden-proof checks for
  Mara's rollback/reconciliation, Elias's bounded/auditable treatment, and
  Nadia's fallback.
- Corrected fixture, README, plan, and design wording: the pair shares each
  concern's scripted initial answer; follow-up delivery is adaptive.

### TDD Evidence

RED:

```bash
cd server && .venv/bin/pytest tests/test_consistency_check.py -k one_sided_followup -v
```

Result: failed as expected. Positional comparison treated the customized
technical follow-up as baseline `cost_realism`, then reported misleading
score-bearing differences.

GREEN:

```bash
cd server && .venv/bin/pytest tests/test_consistency_check.py -k 'compare_baseline or one_sided_followup' -v
cd server && .venv/bin/pytest tests/test_replay_session.py -k discriminator -v
```

Result: 13 baseline-comparison tests passed; 3 discriminator tests passed.

### Verification

```bash
cd server && .venv/bin/pytest tests/test_consistency_check.py tests/test_replay_session.py -v
python3 -m json.tool scripts/replay/scenario-custom-dana.json >/dev/null
python3 -m json.tool scripts/replay/scenario-custom-marcus.json >/dev/null
python3 -m json.tool scripts/replay/scenario-custom-priya.json >/dev/null
git diff --check
```

Result: 46 tests passed; all JSON commands exited 0; diff check passed.

Focused Ruff found two new long format strings, which were split. Full-file Ruff
still reports six pre-existing issues in `scripts/consistency_check.py`: two
`B905` calls without `strict=`, two `UP017` UTC aliases, and two existing long
argparse lines. They are outside this fix round.

### Self-review

- A custom-only follow-up is now an explicit added turn, not compared against
  the next concern.
- Later `cost_realism` turns align by key and do not create a false difference.
- Added or removed answer turns remain score-bearing observations; generic
  consistency comparison behavior remains unchanged.
- No live service was started, and no score outcome is asserted.

## Final Fix: Repeated Clarifications

### Changes

- Baseline alignment now gives non-answer turns a per-concern, per-kind
  occurrence ordinal.
- Answer keys remain `initial` and `follow-up`; repeated clarifications become
  `clarify 1`, `clarify 2`, and so on.
- Added regression coverage where only the first of two same-concern
  clarifications changes its reply.

### TDD Evidence

RED:

```bash
cd server && .venv/bin/pytest tests/test_consistency_check.py -k same_concern_clarification -v
```

Result: failed as expected. The old key collapsed both `clarify` records, so
the changed first reply was absent from the baseline comparison.

GREEN:

```bash
cd server && .venv/bin/pytest tests/test_consistency_check.py -k 'same_concern_clarification or one_sided_followup' -v
```

Result: 2 passed. The first clarification reports as `clarify 1`, and the
one-sided-follow-up alignment remains covered.

### Self-review

- Generic consistency comparison remains positional and unchanged.
- Repeated clarification records cannot overwrite prior records for the same
  concern and kind.
- No API, fixture content, or unrelated persona formatting changed.
