import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

function sseBody(result: unknown): string {
  return (
    `data: ${JSON.stringify({ stage: "extracting" })}\n\n` +
    `data: ${JSON.stringify({ stage: "scoring" })}\n\n` +
    `data: ${JSON.stringify({ stage: "reacting" })}\n\n` +
    `data: ${JSON.stringify({ result })}\n\n`
  )
}

const CLAMPED_ANSWER = {
  reply: "That is not what the PWS says.",
  rationale: "Three refuted counts and no commitment.",
  persona_id: "technical_evaluator",
  concern_id: "technical_approach",
  concern_status: "dodged",
  support_delta: -2,
  raw_support_delta: -5,
  matched_rows: ["dodge", "false_fact"],
  row_counts: { dodge: 1, false_fact: 3 },
  meter: 48,
  capped: false,
  limit: null,
  meters: [
    { persona_id: "technical_evaluator", support: 48, capped: false },
    { persona_id: "contracting_officer", support: 50, capped: false },
    { persona_id: "program_rep", support: 50, capped: false },
  ],
  next_prompt: null,
  done: false,
}

// WCAG 2.1 AA color-contrast check. axe-core's `color-contrast` rule enforces
// the 4.5:1 (normal text) / 3:1 (large text) ratio from success criterion
// 1.4.3. Federal software falls under Section 508, which points at WCAG 2.0/2.1
// AA, so this guards the whole UI against low-contrast regressions as it grows.
//
// Scoped to contrast only for now. Drop `.withRules` and use
// `.withTags(["wcag2a", "wcag2aa", "wcag21aa"])` to widen to a full AA audit.
test("home page has no WCAG 2.1 AA contrast violations", async ({ page }) => {
  await page.goto("/")
  // Wait for steady state so transient loading text is not what gets scanned.
  await expect(page.getByRole("heading", { name: "Airtight" })).toBeVisible()

  // Expand the mic check so its controls are inside the sweep. This project
  // runs without fake media or granted permission, so the panel shows its
  // "Allow microphone access" state — deliberately not clicked, since the point
  // here is contrast, not devices.
  await page.getByTestId("mic-check-toggle").click()
  await expect(page.getByTestId("mic-check")).toBeVisible()

  const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze()

  expect(results.violations).toEqual([])
})

test("the scored transcript has no color-contrast violations", async ({ page }) => {
  await page.route("**/api/sessions/*/answer/stream", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: sseBody(CLAMPED_ANSWER),
    }),
  )

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByPlaceholder("Your answer…").fill("Twelve million records, three waves.")
  await page.getByRole("button", { name: "Submit" }).click()
  await expect(page.getByText("Max · from -5")).toBeVisible()

  const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze()
  expect(results.violations).toEqual([])
})
