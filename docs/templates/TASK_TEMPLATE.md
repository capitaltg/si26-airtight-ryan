# Task template

For a single implementation task, in the shape the Airtight implementation plan
uses (`docs/superpowers/plans/2026-07-17-airtight-poc-implementation.md`).
Follow it exactly. Tasks are TDD-first: the failing test comes before the code.

---

## Task: <short title>

**Goal:** One sentence on what this task delivers.

**Files:**
- Create: `path/to/new_file.py`
- Modify: `path/to/existing.py`
- Test: `path/to/test_file.py`

**Interfaces:**
- Produces: the function/class/endpoint this task exposes, with its signature.
- Consumes: what it depends on from earlier tasks.

**Steps:**
- [ ] Step 1: Write the failing test that pins the behavior.
- [ ] Step 2: Run it, confirm it fails for the right reason.
- [ ] Step 3: Implement the minimum to pass.
- [ ] Step 4: Run the test, confirm it passes.
- [ ] Step 5: Run the wider check (`ruff`/`mypy`/`pytest`, or `npm run build`).
- [ ] Step 6: Commit with a Conventional Commits message.

**Exit:** The observable condition that means the task is done and verified.
