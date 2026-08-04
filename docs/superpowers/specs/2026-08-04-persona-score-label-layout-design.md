# Persona Score Label Layout Design

## Scope

Make each locked exemplar score label easier to scan in the persona editor.

## Design

- Preserve the current score label text and read-only behavior.
- Make the label span both columns of the exemplar details grid.
- Increase the label to the standard body size and use a semibold weight.
- Keep the existing test id and the save payload unchanged.

## Verification

Browser coverage will assert that the label uses the full-width grid placement and
the larger text treatment. Existing coverage continues to prove the label is not
editable and is preserved in the save payload.
