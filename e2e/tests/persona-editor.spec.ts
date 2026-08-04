import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

// Every request the editor makes is mocked. The suite is fullyParallel and the
// persona store is global to the stack, so a real save here would change the
// personas out from under the specs running beside it. The write path itself is
// covered by server/tests/test_api_personas.py.

const MARCUS = {
  id: "contracting_officer",
  display_name: "Marcus",
  intro: "Marcus Reyes, contracting officer on this acquisition.",
  voice: "Formal and careful.",
  demographics: "Contracting officer with warrant authority.",
  values: ["compliance with the RFP"],
  wants: ["answers that stay inside the PWS"],
  priorities: ["compliance_security", "cost_realism", "past_performance"],
  non_negotiables: ["do not promise work outside the PWS"],
  rubric_version: 1,
  polly_voice_id: "Matthew",
  exemplars: [
    {
      persona: "contracting_officer",
      user: "Firm-fixed price, 28 FTE.",
      support_delta: 2,
      note: "Backed.",
    },
  ],
  is_customized: false,
}

const DANA = { ...MARCUS, id: "technical_evaluator", display_name: "Dana", exemplars: [] }

async function mockList(page: import("@playwright/test").Page, personas: unknown[]) {
  await page.route("**/api/content/personas", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(personas) }),
  )
}

async function openEditor(page: import("@playwright/test").Page) {
  await page.goto("/")
  await page.getByTestId("open-persona-editor").click()
  await expect(page.getByRole("heading", { name: "Personas" })).toBeVisible()
}

test("the form pre-fills from the server and shows the locked fields read-only", async ({
  page,
}) => {
  await mockList(page, [DANA, MARCUS])
  await openEditor(page)
  await page.getByTestId("toggle-contracting_officer").click()

  await expect(page.getByTestId("field-display_name")).toHaveValue("Marcus")
  const pollyVoice = page.getByTestId("field-polly_voice_id")
  await expect(pollyVoice).toHaveValue("Matthew")
  await expect(pollyVoice).toHaveJSProperty("tagName", "SELECT")
  await expect(pollyVoice.locator("option")).toHaveCount(3)
  await expect(pollyVoice.locator('option[value="Matthew"]')).toHaveCount(1)
  await expect(pollyVoice.locator('option[value="Ruth"]')).toHaveCount(1)
  await expect(pollyVoice.locator('option[value="Danielle"]')).toHaveCount(1)
  await expect(page.getByTestId("field-intro")).toHaveValue(
    "Marcus Reyes, contracting officer on this acquisition.",
  )
  const supportDelta = page.getByTestId("exemplar-delta-0")
  await expect(supportDelta).toHaveText("+2")
  await expect(supportDelta).toHaveJSProperty("tagName", "P")
  await expect(supportDelta).toHaveCSS("font-size", "14px")
  const [scoreBox, detailsBox] = await Promise.all([
    supportDelta.boundingBox(),
    supportDelta.locator("..").boundingBox(),
  ])
  expect(scoreBox!.width).toBeLessThan(detailsBox!.width)
  await expect(page.locator('input[data-testid="exemplar-delta-0"]')).toHaveCount(0)
  await expect(page.getByTestId("locked-id")).toHaveText("contracting_officer")
  await expect(page.getByTestId("locked-rubric-version")).toHaveText("1")
  // Locked fields render as text, not inputs — there is nothing to type into.
  await expect(page.getByTestId("locked-priorities")).toHaveJSProperty("tagName", "DD")
  await expect(page.getByTestId("locked-id")).toHaveJSProperty("tagName", "DD")
})

test("saving PUTs only the editable fields", async ({ page }) => {
  await mockList(page, [MARCUS])
  let sent: Record<string, unknown> | null = null
  await page.route("**/api/content/personas/contracting_officer", async (route) => {
    sent = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...MARCUS, display_name: "Mira", is_customized: true }),
    })
  })

  await openEditor(page)
  await page.getByTestId("toggle-contracting_officer").click()
  await page.getByTestId("field-display_name").fill("Mira")
  await page.getByTestId("field-polly_voice_id").selectOption("Ruth")
  await page.getByRole("button", { name: "Save persona" }).click()

  await expect(page.getByRole("status")).toHaveText("Saved")
  expect(sent).not.toBeNull()
  expect(sent!.display_name).toBe("Mira")
  expect(sent).not.toHaveProperty("id")
  expect(sent).not.toHaveProperty("priorities")
  expect(sent).not.toHaveProperty("rubric_version")
  expect(sent!.polly_voice_id).toBe("Ruth")
  // Exemplars go up without a persona — the server stamps it.
  expect(sent!.exemplars).toEqual([
    { user: "Firm-fixed price, 28 FTE.", support_delta: 2, note: "Backed." },
  ])
})

test("a 422 renders against the editable exemplar field that caused it", async ({ page }) => {
  await mockList(page, [MARCUS])
  await page.route("**/api/content/personas/contracting_officer", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: [
          {
            loc: ["body", "exemplars", 0, "note"],
            msg: "Note is required",
            type: "missing",
          },
        ],
      }),
    }),
  )

  await openEditor(page)
  await page.getByTestId("toggle-contracting_officer").click()
  await page.getByRole("button", { name: "Save persona" }).click()

  await expect(page.getByRole("alert")).toHaveText("Note is required")
  await expect(page.getByRole("status")).toHaveCount(0)
})

test("a non-validation failure is a banner, not a field error", async ({ page }) => {
  await mockList(page, [MARCUS])
  await page.route("**/api/content/personas/contracting_officer", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "could not write the persona file" }),
    }),
  )

  await openEditor(page)
  await page.getByTestId("toggle-contracting_officer").click()
  await page.getByRole("button", { name: "Save persona" }).click()

  await expect(page.getByTestId("persona-editor-error")).toHaveText(
    "could not write the persona file",
  )
})

test("reset asks first, and cancelling sends nothing", async ({ page }) => {
  const customized = { ...MARCUS, display_name: "Mira", is_customized: true }
  await mockList(page, [customized])
  let resetCalls = 0
  await page.route("**/api/content/personas/contracting_officer/reset", async (route) => {
    resetCalls += 1
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MARCUS),
    })
  })

  await openEditor(page)
  await expect(page.getByTestId("customized-contracting_officer")).toBeVisible()
  await page.getByTestId("toggle-contracting_officer").click()

  await page.getByTestId("reset-contracting_officer").click()
  await expect(page.getByTestId("confirm-reset")).toBeVisible()
  await page.getByTestId("confirm-reset-cancel").click()
  await expect(page.getByTestId("confirm-reset")).toHaveCount(0)
  expect(resetCalls).toBe(0)

  await page.getByTestId("reset-contracting_officer").click()
  await page.getByTestId("confirm-reset-confirm").click()
  await expect.poll(() => resetCalls).toBe(1)
})

test("confirming a reset restores the shipped values in the form", async ({ page }) => {
  const customized = { ...MARCUS, display_name: "Mira", is_customized: true }
  let listed = [customized]
  await page.route("**/api/content/personas", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(listed) }),
  )
  await page.route("**/api/content/personas/contracting_officer/reset", async (route) => {
    listed = [MARCUS]
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MARCUS),
    })
  })

  await openEditor(page)
  await page.getByTestId("toggle-contracting_officer").click()
  await expect(page.getByTestId("field-display_name")).toHaveValue("Mira")

  await page.getByTestId("reset-contracting_officer").click()
  await page.getByTestId("confirm-reset-confirm").click()

  await expect(page.getByTestId("field-display_name")).toHaveValue("Marcus")
  await expect(page.getByTestId("customized-contracting_officer")).toHaveCount(0)
})

// The editor is a pre-rehearsal surface. A running session has already fixed its
// evaluators and its agenda, so there is deliberately no way into the editor from
// the rehearsal screen — see docs/specs/2026-08-04-landing-layout-design.md §3.1a.
test("a running rehearsal offers no way into the persona editor", async ({ page }) => {
  await mockList(page, [DANA, MARCUS])
  await page.goto("/")
  await expect(page.getByTestId("open-persona-editor")).toBeVisible()

  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await expect(page.getByRole("button", { name: "How you're scored" })).toBeVisible()

  await expect(page.getByTestId("open-persona-editor")).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "Personas" })).toHaveCount(0)
})

test("the editor has no WCAG 2.1 AA contrast violations", async ({ page }) => {
  await mockList(page, [DANA, MARCUS])
  await openEditor(page)
  await page.getByTestId("toggle-contracting_officer").click()
  await expect(page.getByTestId("field-display_name")).toBeVisible()

  const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze()
  expect(results.violations).toEqual([])
})
