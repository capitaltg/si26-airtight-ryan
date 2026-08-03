# Persona Customization Replays — Design

## Goal

Add three runnable fixtures under `scripts/replay/` that demonstrate how a
customized evaluator changes the rehearsal experience without changing the
fixed scenario structure or scoring ownership. Add an opt-in comparison that
runs the same fixture with default and customized personas, then shows their
scoring and reaction differences.

## Approach

Extend `scripts/replay_session.py` with an optional top-level `personas`
mapping. Before creating a session, the runner reads each named live persona,
overlays the mapping's editable fields, and calls `PUT /content/personas/{id}`.
It records the original editable payloads. In a `finally` block it restores
those payloads, even if the rehearsal request fails. The runner never sends
`id`, `priorities`, or `rubric_version`.

Each scenario remains a normal concern-keyed session fixture. Its `personas`
mapping only controls the temporary customizations applied around that run.
The existing scenarios retain their current behavior because the mapping is
optional.

`scripts/consistency_check.py --compare-baseline` snapshots every live persona
targeted by the scenario, resets those IDs through the existing content API,
then runs the same answers first against shipped defaults and next against the
temporary override. The override starts from the reset default state. A final
cleanup restores every pre-comparison snapshot, including when reset, replay,
or response handling fails. It reports changed matched rows, deltas, meters,
statuses, replies, and rationales. A comparison with no differences still
succeeds. The comparison observes a result; it does not claim that a persona
edit must change a score.

## Fixtures

- `scenario-custom-dana.json`: incisive architecture and transition focus.
- `scenario-custom-marcus.json`: strict terms, scope, and price-realism focus.
- `scenario-custom-priya.json`: continuity, support, and frontline-user focus.

Every fixture exercises a complete eight-concern run and changes only editable
persona character fields. Notes describe the temporary nature of the edit and
the intended evaluator behavior. No fixture declares a scoring-row expectation:
persona character can affect model extraction and reaction, while deterministic
scoring remains owned by the rubric once extraction facts are validated.

## Failure handling and testing

If applying a customization fails, the runner stops before creating a session.
It registers the target snapshot before each `PUT`, so a saved update is still
restored when response handling fails. If a scenario omits exemplars, the apply
payload retains the snapshot's complete exemplar set. If replaying fails,
restoration still runs. Restoration failures are reported alongside the
original failure.

Unit tests cover payload filtering, applying multiple customizations, and
restoration after both success and replay failure. Existing scenarios verify
backward compatibility. The three fixtures are validated as JSON and exercised
against a running API when available. Comparison tests use fabricated baseline
and customized run records to verify both score-bearing and reaction-only
differences are reported, without requiring a difference to pass.
