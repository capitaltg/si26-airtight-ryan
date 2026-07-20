# PR template

Canonical pull-request writeup for Airtight. Follow it exactly when asked to
write a PR. The GitHub-rendered copy at `.github/PULL_REQUEST_TEMPLATE.md`
mirrors this file; keep the two in sync when either changes.

---

## Summary

One or two sentences: what this PR does and why. Lead with the change, not the
history.

## Related

- Closes #<issue>, or links the task/plan section it implements
  (`docs/superpowers/plans/...#task-N`).

## Type

Pick one (matches the Conventional Commits type on the squash commit):
`feat` | `fix` | `refactor` | `test` | `docs` | `chore` | `perf` | `ci`.

## Changes

- Bullet the concrete changes, grouped by area (server / frontend / e2e / docs).
- Name the files or modules that carry the load, not every line.

## Verification

State what you ran and the result. Evidence, not assertions.

- [ ] Server: `ruff check .`, `mypy app`, `pytest -v` pass
- [ ] Frontend: `npm run build` (typecheck + build) passes
- [ ] E2E: `npm run e2e` passes (or N/A, say why)
- [ ] Manual check: <what you drove and what you observed> (or N/A)

## Scoring-engine impact

The number must stay code-owned and deterministic. Tick what applies:

- [ ] No change to extraction schema, scoring engine, or the rubric
- [ ] Scoring changed and the golden-set regression test still passes
- [ ] No model call computes or influences the score

## Notes and risks

Anything a reviewer should know: tradeoffs, follow-ups, deferred work, or
"nothing here" if there is nothing.
