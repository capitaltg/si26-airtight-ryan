import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

// The sweep the token layer was supposed to buy: a11y-contrast.spec.ts covers
// one state of one screen, and the gallery covers components in isolation.
// Neither would catch a full-height bg-white wrapper on a real screen, which is
// the most likely regression from the restyle (spec §3.2, §5.3).
//
// Fixtures are copied from the specs that already own them — session-history for
// history and archive, a11y-contrast for an in-session scored turn — so this
// spec cannot drift onto backend shapes nothing else exercises.

const SAND_50 = "rgb(245, 241, 236)"

type Page = import("@playwright/test").Page

async function expectSandGround(page: Page) {
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  expect(bg).toBe(SAND_50)
}

async function expectNoContrastViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze()
  expect(results.violations).toEqual([])
}

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

const ARCHIVED_ID = "11111111-2222-3333-4444-555555555555"

const HISTORY = [
  {
    id: ARCHIVED_ID,
    created_at: "2026-07-28T12:00:00Z",
    archived_at: "2026-07-28T12:40:00Z",
    status: "complete",
    turn_count: 8,
    meters: [
      { persona_id: "technical_evaluator", support: 58, capped: false },
      { persona_id: "contracting_officer", support: 46, capped: false },
      { persona_id: "program_rep", support: 52, capped: false },
    ],
    concerns_satisfied: 7,
    concerns_total: 8,
  },
]

const TRANSCRIPT = {
  turns: [
    {
      persona_id: "technical_evaluator",
      display_name: "Dana",
      concern_id: "technical_approach",
      is_follow_up: false,
      prompt: "Walk me through the architecture you are proposing.",
      intro: null,
      answer: "Three services behind a FedRAMP-authorized host.",
      reply: "Concrete enough. Noted.",
      rationale: "Backed specifics on all three sub-questions.",
      support_delta: 2,
      matched_rows: ["evidence_backed"],
      capped: false,
      scored: true,
      transcript: null,
    },
  ],
}

// A capped persona, an over-limit finding, a clarification, and a scored finding
// with a quote: the four blocks of the report that carry their own tone.
const REPORT = {
  session_id: ARCHIVED_ID,
  status: "complete",
  rate_stats: {
    total_turns: 8,
    dodge_count: 1,
    dodges_per_turn: 0.125,
    contradiction_count: 0,
    concerns_total: 8,
    concerns_satisfied: 7,
    coverage_rate: 0.875,
    concerns_by_status: { satisfied: 7, partial_exhausted: 0, dodged: 0, breached: 1 },
  },
  personas: [{ persona_id: "technical_evaluator", support: 25, capped: true }],
  coverage_counts: { full: 20, partial: 3, none: 1 },
  dodge_counts_by_type: { non_commitment: 1 },
  contradiction_count: 0,
  findings: [
    {
      turn_index: 2,
      persona_id: "technical_evaluator",
      concern_id: "technical_approach",
      rubric_row: "dodge",
      support_value: -1,
      count: 1,
      evidence: [{ span: "We would look at that closer to award.", detail: "non_commitment" }],
    },
  ],
  limit_findings: [
    {
      turn_index: 3,
      persona_id: "technical_evaluator",
      concern_id: "technical_approach",
      kind: "text_words",
      measured: 240,
      limit_threshold: 200,
      penalty: 1,
    },
  ],
  clarifications: [
    {
      persona_id: "contracting_officer",
      concern_id: "cost_realism",
      question: "Do you mean the option years?",
      reply: "Base year only.",
    },
  ],
  score_audit: [
    {
      turn_index: 2,
      persisted_support_delta: -1,
      recomputed_support_delta: -1,
      persisted_matched_rows: ["dodge"],
      recomputed_matched_rows: ["dodge"],
      agrees: true,
    },
  ],
  score_audit_agrees: true,
  narrative: { scored: false, header: "Not scored", text: "You held the technical line." },
}

function stubHistory(page: Page) {
  return Promise.all([
    page.route("**/api/sessions/history", (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(HISTORY),
      }),
    ),
    page.route(`**/api/sessions/${ARCHIVED_ID}/transcript`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(TRANSCRIPT),
      }),
    ),
    page.route(`**/api/sessions/${ARCHIVED_ID}/report`, (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "application/json" },
        body: JSON.stringify(REPORT),
      }),
    ),
  ])
}

test("landing screen", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Airtight" })).toBeVisible()
  await expectSandGround(page)
  await expectNoContrastViolations(page)
})

test("persona editor", async ({ page }) => {
  await page.goto("/")
  await page.getByTestId("open-persona-editor").click()
  await expect(page.getByRole("heading", { name: "Personas" })).toBeVisible()
  await expectSandGround(page)
  await expectNoContrastViolations(page)
})

test("history list and archive view", async ({ page }) => {
  await stubHistory(page)
  await page.goto("/")
  await expect(page.getByTestId("history-card")).toBeVisible()
  await expectSandGround(page)
  await expectNoContrastViolations(page)

  await page.getByTestId("history-card").click()
  await expect(page.getByTestId("archive-view")).toBeVisible()
  await expect(page.getByText("Red line crossed.")).toBeVisible()
  await expectSandGround(page)
  await expectNoContrastViolations(page)
})

test("rehearsal in session, and the rubric drawer over it", async ({ page }) => {
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
  await expectSandGround(page)
  await expectNoContrastViolations(page)

  // No other spec sweeps the drawer, and it is the densest text surface in the
  // app, so this is its only automated contrast coverage.
  await page.getByRole("button", { name: "How you're scored" }).click()
  await expect(page.getByRole("dialog", { name: "How you're scored" })).toBeVisible()
  await expect(page.getByText("Scoring rows")).toBeVisible()
  await expectNoContrastViolations(page)
})
