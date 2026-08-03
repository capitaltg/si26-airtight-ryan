# Persona Customization Replays — Design

## Goal

Add three runnable fixtures under `scripts/replay/` that demonstrate how a
customized evaluator changes the rehearsal experience without changing the
fixed scenario structure or scoring ownership.

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

## Fixtures

- `scenario-custom-dana.json`: incisive architecture and transition focus.
- `scenario-custom-marcus.json`: strict terms, scope, and price-realism focus.
- `scenario-custom-priya.json`: continuity, support, and frontline-user focus.

Every fixture exercises a complete eight-concern run and changes only editable
persona character fields. Notes describe the temporary nature of the edit and
the intended evaluator behavior. No fixture declares a scoring-row expectation:
persona character affects model reaction, while deterministic scoring remains
owned by the rubric.

## Failure handling and testing

If applying a customization fails, the runner stops before creating a session
and restores any personas already updated. If replaying fails, restoration still
runs. Restoration failures are reported alongside the original failure.

Unit tests cover payload filtering, applying multiple customizations, and
restoration after both success and replay failure. Existing scenarios verify
backward compatibility. The three fixtures are validated as JSON and exercised
against a running API when available.
