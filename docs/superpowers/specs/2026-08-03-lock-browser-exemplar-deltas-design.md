# Lock Browser Exemplar Score Labels — Design

## Goal

Prevent browser-editor users from changing an exemplar's `support_delta`.
Keep the authored label visible so users can understand how the example is
calibrated. Preserve all replay-fixture and content-API behavior.

## Scope

The persona form replaces each editable numeric delta input with read-only
text, for example `Score calibration: +2 (locked)`. The form still permits
users to add, remove, and edit exemplar answer and note text. On save, it
sends the existing label for every retained exemplar; editing other fields
cannot alter it through the browser UI.

`PersonaUpdate`, `ExemplarUpdate`, the persona writer, and the replay runner
remain unchanged. This keeps the content API available to the replay harness,
whose temporary authored override payloads include their explicit calibration
labels. The API remains the validation boundary for `-2` through `2`.

## Data flow

The browser receives each label in `Persona.exemplars`. `toDraft` retains that
value in the local save payload, but PersonaForm exposes no event that mutates
it. New exemplars receive the existing neutral `0` label, also locked. The
PUT payload therefore remains compatible with the current API and writer.

## Error handling

No browser field maps server validation errors for
`exemplars.<index>.support_delta`, because the control is absent. Errors for
the editable exemplar answer and note fields continue to display as today.
An out-of-band client or replay request remains subject to existing server
range validation.

## Tests

Update the persona-editor browser test to assert that the delta uses
non-editable text rather than a number input, and that saving the form sends
the original delta. Keep coverage for server-side range errors as API behavior
and retain replay tests unchanged.
