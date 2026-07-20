<!--
Mirror of docs/templates/PR_TEMPLATE.md. Keep the two in sync.
GitHub prefills this into every new PR description.
-->

## Summary

<!-- One or two sentences: what this PR does and why. -->

## Related

<!-- Closes #<issue>, or link the task/plan section it implements. -->

## Type

<!-- feat | fix | refactor | test | docs | chore | perf | ci -->

## Changes

<!-- Concrete changes grouped by area (server / frontend / e2e / docs). -->
-

## Verification

<!-- What you ran and the result. Evidence, not assertions. -->
- [ ] Server: `ruff check .`, `mypy app`, `pytest -v` pass
- [ ] Frontend: `npm run build` passes
- [ ] E2E: `npm run e2e` passes (or N/A, say why)
- [ ] Manual check: <what you drove and observed> (or N/A)

## Scoring-engine impact

<!-- The number stays code-owned and deterministic. Tick what applies. -->
- [ ] No change to extraction schema, scoring engine, or the rubric
- [ ] Scoring changed and the golden-set regression test still passes
- [ ] No model call computes or influences the score

## Notes and risks

<!-- Tradeoffs, follow-ups, deferred work, or "nothing here". -->
