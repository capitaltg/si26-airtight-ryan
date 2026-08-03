# Lock Browser Exemplar Score Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make exemplar score calibration visible but non-editable in the browser persona editor while preserving its save payload.

**Architecture:** Keep `support_delta` in the existing `PersonaUpdate` draft so the browser sends the server-provided value on every save. Replace only PersonaForm's editable number control with semantic read-only text. Leave the content API, persona writer, and replay payloads unchanged.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Playwright.

## Global Constraints

- Scope is browser editor only; replay fixtures and content API support-delta behavior remain unchanged.
- The server owns score calibration range validation: `support_delta` remains an integer from `-2` through `2`.
- Browser users can still add, remove, and edit exemplar answer and note text.
- New browser exemplars use the existing neutral `0` support delta and cannot change it through the UI.
- Do not add dependencies or new files outside this plan and its existing test/component targets.

---

## File Structure

- `frontend/src/components/PersonaForm.tsx` owns editor draft state and exemplar controls. It will render locked score calibration text while retaining `support_delta` in its save draft.
- `e2e/tests/persona-editor.spec.ts` owns mocked browser coverage for persona editing. It will prove the label is visible, non-editable, and unchanged in the outgoing PUT payload.

### Task 1: Render Locked Exemplar Calibration

**Files:**

- Modify: `e2e/tests/persona-editor.spec.ts:37-122`
- Modify: `frontend/src/components/PersonaForm.tsx:197-260`

**Interfaces:**

- Consumes: `Persona.exemplars: PersonaExemplar[]`, where each `PersonaExemplar` includes `support_delta: number`.
- Produces: `PersonaForm` renders `data-testid="exemplar-delta-${i}"` as non-form text and keeps `PersonaUpdate.exemplars[number].support_delta` unchanged in the submitted draft.

- [ ] **Step 1: Write the failing browser tests**

  In `e2e/tests/persona-editor.spec.ts`, replace the editable-number assertions with:

  ```ts
  const supportDelta = page.getByTestId("exemplar-delta-0")
  await expect(supportDelta).toHaveText("Score calibration: +2 (locked)")
  await expect(supportDelta).toHaveJSProperty("tagName", "OUTPUT")
  await expect(page.locator('input[data-testid="exemplar-delta-0"]')).toHaveCount(0)
  ```

  In the save test, edit `field-display_name`, click **Save persona**, and retain this assertion:

  ```ts
  expect(sent!.exemplars).toEqual([
    { user: "Firm-fixed price, 28 FTE.", support_delta: 2, note: "Backed." },
  ])
  ```

  Replace the old support-delta 422 test with an editable note validation error:

  ```ts
  loc: ["body", "exemplars", 0, "note"],
  msg: "Note is required",
  type: "missing",
  ```

  Assert the note error is shown after save. Do not add a client-side
  `support_delta` error assertion because the browser exposes no such field.

- [ ] **Step 2: Run the focused browser test to verify it fails**

  Run:

  ```bash
  cd e2e && npm test -- persona-editor.spec.ts
  ```

  Expected: FAIL because `exemplar-delta-0` is still an editable `INPUT` whose
  text is not `Score calibration: +2 (locked)`.

- [ ] **Step 3: Replace the numeric input with semantic locked text**

  In the exemplar card in `frontend/src/components/PersonaForm.tsx`, replace
  the support-delta `<label>` and number `<input>` with:

  ```tsx
  <output
    className="block rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-700"
    data-testid={`exemplar-delta-${i}`}
  >
    Score calibration: {exemplar.support_delta >= 0 ? "+" : ""}
    {exemplar.support_delta} (locked)
  </output>
  ```

  Remove the `onChange` call and `FieldMessage` for
  `exemplars.${i}.support_delta`. Keep `support_delta` in `toDraft`,
  `setExemplar`, and the new-exemplar object so existing save behavior sends
  the unchanged label and new exemplars retain `0`.

- [ ] **Step 4: Run focused browser coverage to verify it passes**

  Run:

  ```bash
  cd e2e && npm test -- persona-editor.spec.ts
  ```

  Expected: PASS. The mocked PUT body still contains `support_delta: 2`; no
  browser input can mutate it.

- [ ] **Step 5: Run frontend static checks**

  Run:

  ```bash
  cd frontend && npm run build
  ```

  Expected: PASS with TypeScript compilation and Vite production build.

- [ ] **Step 6: Commit the completed task**

  ```bash
  git add frontend/src/components/PersonaForm.tsx e2e/tests/persona-editor.spec.ts
  git commit -m "feat: lock exemplar score labels in editor"
  ```

## Plan Self-Review

- Spec coverage: Task 1 makes calibration visible and non-editable, preserves
  the existing PUT payload, keeps answer/note editing and neutral new-exemplar
  defaults, and deliberately excludes replay/API changes.
- Placeholder scan: no deferred markers or implementation directions.
- Type consistency: `PersonaExemplar.support_delta`,
  `PersonaUpdate.exemplars[number].support_delta`, and the existing
  `exemplar-delta-${i}` test id remain unchanged; only rendered element type
  changes from `INPUT` to `OUTPUT`.
