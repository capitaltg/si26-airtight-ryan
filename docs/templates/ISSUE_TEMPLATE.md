# Issue template (for Claude)

Use this when asked to write up an issue. Follow it exactly. Fill every section
or write "none" so a reader can tell the section was considered, not skipped.

---

## Title

One line, imperative or noun phrase. Specific enough to skim in a list.

## Context

What is the current state, and what prompted this? Link the plan, spec, or code
that frames it (`docs/plans/...`, `docs/superpowers/...`, `file_path:line`).

## Problem or goal

What is wrong or wanted, stated plainly. If it is a bug, give the observed
behavior and the expected behavior.

## Proposed approach

The intended fix or build, if known. Say "open" if it needs design first.

## Acceptance criteria

- [ ] Concrete, checkable conditions that mean this is done.
- [ ] Include the verification that proves it (test, command, observed behavior).

## Affected areas

Server / frontend / e2e / docs / CI / content. Name the ones this touches.

## Out of scope

What this issue deliberately does not cover, so it does not sprawl.

## References

Links to plans, specs, prior issues, or external docs.
