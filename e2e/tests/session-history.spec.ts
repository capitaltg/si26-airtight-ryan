import { expect, test } from "@playwright/test"

// The e2e stack boots without AWS credentials, so no session can reach `done`
// here. These routes are stubbed to exercise the history UI contract; that a
// real finish archives the session is covered by the server tests
// (server/tests/test_api.py).
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
      matched_rows: ["backed_specific"],
      capped: false,
      scored: true,
      transcript: null,
    },
  ],
}

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
    concerns_by_status: { satisfied: 7, partial_exhausted: 1, dodged: 0, breached: 0 },
  },
  personas: [{ persona_id: "technical_evaluator", support: 58, capped: false }],
  coverage_counts: { full: 20, partial: 3, none: 1 },
  dodge_counts_by_type: { non_commitment: 1 },
  contradiction_count: 0,
  findings: [],
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
  clarifications: [],
  score_audit: [
    {
      turn_index: 0,
      persisted_support_delta: 2,
      recomputed_support_delta: 2,
      persisted_matched_rows: ["backed_specific"],
      recomputed_matched_rows: ["backed_specific"],
      agrees: true,
    },
  ],
  score_audit_agrees: true,
  narrative: { scored: false, header: "Not scored", text: "You held the technical line." },
}

function stubHistory(page: import("@playwright/test").Page) {
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

test("the landing screen lists past rehearsals", async ({ page }) => {
  await stubHistory(page)
  await page.goto("/")

  await expect(page.getByTestId("history-list")).toBeVisible()
  const card = page.getByTestId("history-card")
  await expect(card).toHaveCount(1)
  await expect(card).toContainText("Complete")
  await expect(card).toContainText("7 of 8 concerns satisfied")
})

test("opening a past rehearsal shows its transcript and its report", async ({ page }) => {
  await stubHistory(page)
  await page.goto("/")

  await page.getByTestId("history-card").click()

  const archive = page.getByTestId("archive-view")
  await expect(archive).toBeVisible()
  await expect(archive).toContainText("Walk me through the architecture you are proposing.")
  await expect(archive).toContainText("Three services behind a FedRAMP-authorized host.")
  await expect(archive).toContainText("Concrete enough. Noted.")
  // The archived report renders below the transcript.
  await expect(page.getByRole("heading", { name: "After-action report" })).toBeVisible()
  await expect(archive).toContainText("You held the technical line.")
  // Over-limit turns keep their own section in the archived report.
  await expect(archive).toContainText("Answer limits")
  await expect(archive).toContainText("240 words (200 words limit)")
  // The breakdown that keeps "the rehearsal finished" from reading as "the
  // rubric was met".
  await expect(archive).toContainText("Concern outcomes")
  await expect(archive).toContainText("Partial, attempts used")
  await expect(archive).toContainText("Complete means every concern used up its attempts")

  await page.getByRole("button", { name: "← Back" }).click()
  await expect(page.getByRole("button", { name: "Start rehearsal" })).toBeVisible()
})

test("with no history the list shows its empty state", async ({ page }) => {
  await page.route("**/api/sessions/history", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: "[]",
    }),
  )
  await page.goto("/")

  await expect(page.getByTestId("history-list")).toContainText("Finished rehearsals appear here")
  await expect(page.getByTestId("history-card")).toHaveCount(0)
})
