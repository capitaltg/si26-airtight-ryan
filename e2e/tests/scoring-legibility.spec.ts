import { expect, test } from "@playwright/test"

function sseBody(result: unknown): string {
  return (
    `data: ${JSON.stringify({ stage: "extracting" })}\n\n` +
    `data: ${JSON.stringify({ stage: "scoring" })}\n\n` +
    `data: ${JSON.stringify({ stage: "reacting" })}\n\n` +
    `data: ${JSON.stringify({ result })}\n\n`
  )
}

function answer(over: Record<string, unknown>) {
  return {
    reply: "That is not what the PWS says.",
    rationale: "Three refuted counts and no commitment.",
    persona_id: "technical_evaluator",
    concern_id: "technical_approach",
    concern_status: "dodged",
    support_delta: -2,
    raw_support_delta: -2,
    matched_rows: ["dodge"],
    row_counts: { dodge: 1 },
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
    ...over,
  }
}

async function submitOnce(page: import("@playwright/test").Page, result: unknown) {
  await page.route("**/api/sessions/*/answer/stream", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: sseBody(result),
    }),
  )
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByPlaceholder("Your answer…").fill("Twelve million records, three waves.")
  await page.getByRole("button", { name: "Submit" }).click()
}

test("a multiplied row shows its count and the clamp shows what it absorbed", async ({ page }) => {
  await submitOnce(
    page,
    answer({
      support_delta: -2,
      raw_support_delta: -5,
      matched_rows: ["dodge", "false_fact"],
      row_counts: { dodge: 1, false_fact: 3 },
    }),
  )

  await expect(page.getByText("False Fact x3")).toBeVisible()
  await expect(page.getByText("Dodge", { exact: true })).toBeVisible()
  await expect(page.getByText("Dodge x1")).toHaveCount(0)
  await expect(page.getByText("Max · from -5")).toBeVisible()
})

test("a turn at the bound says Max without a from", async ({ page }) => {
  await submitOnce(page, answer({ support_delta: -2, raw_support_delta: -2 }))

  await expect(page.getByText("Max", { exact: true })).toBeVisible()
  await expect(page.getByText("from -2")).toHaveCount(0)
})

test("a turn inside the bound shows no marker", async ({ page }) => {
  await submitOnce(
    page,
    answer({
      support_delta: -1,
      raw_support_delta: -1,
      matched_rows: ["false_fact"],
      row_counts: { false_fact: 1 },
      concern_status: "partial",
    }),
  )

  await expect(page.getByText("False Fact", { exact: true })).toBeVisible()
  await expect(page.getByText("Max")).toHaveCount(0)
})

test("the rubric drawer discloses how rows combine", async ({ page }) => {
  await page.route("**/api/content/rubric", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        version: 2,
        rows: [
          {
            id: "false_fact",
            description: "Stated a fact that turned out false.",
            support_value: -1,
            cap: null,
            note: "Charged once per false fact, unlike every other row.",
          },
          {
            id: "dodge",
            description: "Dodged the main question.",
            support_value: -2,
            cap: null,
            note: null,
          },
        ],
        combination: [
          "A red line fires first and suppresses every other row on that answer.",
          "All other matching rows are added together, then held to the -2 to +2 range.",
        ],
        concerns: [],
      }),
    }),
  )

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByRole("button", { name: "How you're scored" }).click()

  await expect(page.getByText("How rows combine")).toBeVisible()
  await expect(page.getByText("A red line fires first")).toBeVisible()
  await expect(page.getByText("Charged once per false fact")).toBeVisible()
})

test("an archived turn renders counts and the marker", async ({ page }) => {
  const sessionId = "11111111-1111-1111-1111-111111111111"
  await page.route("**/api/sessions/history", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify([
        {
          id: sessionId,
          status: "complete",
          created_at: "2026-07-30T12:00:00Z",
          archived_at: "2026-07-30T12:40:00Z",
          turn_count: 1,
          meters: [{ persona_id: "technical_evaluator", support: 48, capped: false }],
          concerns_satisfied: 1,
          concerns_total: 8,
        },
      ]),
    }),
  )
  await page.route(`**/api/sessions/${sessionId}/transcript`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        turns: [
          {
            persona_id: "technical_evaluator",
            display_name: "Dana",
            concern_id: "technical_approach",
            is_follow_up: false,
            prompt: "Walk me through the architecture you are proposing.",
            intro: null,
            answer: "Twelve million records, three waves.",
            reply: "That is not what the PWS says.",
            rationale: "Two refuted counts.",
            support_delta: -2,
            raw_support_delta: -4,
            matched_rows: ["false_fact"],
            row_counts: { false_fact: 2 },
            capped: false,
            scored: true,
            transcript: null,
            limit: null,
          },
        ],
      }),
    }),
  )
  await page.route(`**/api/sessions/${sessionId}/report`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        status: "complete",
        rate_stats: {
          total_turns: 1,
          dodge_count: 0,
          dodges_per_turn: 0,
          contradiction_count: 0,
          concerns_total: 8,
          concerns_satisfied: 1,
          coverage_rate: 0.125,
        },
        personas: [],
        coverage_counts: { full: 0, partial: 0, none: 0 },
        dodge_counts_by_type: {},
        contradiction_count: 0,
        // A pre-grouping archived snapshot upgrades each old finding separately.
        // Same (turn, row) must still render both cards without a React key collision.
        findings: [
          {
            turn_index: 0,
            persona_id: "technical_evaluator",
            concern_id: "technical_approach",
            rubric_row: "false_fact",
            support_value: -1,
            count: 1,
            evidence: [{ span: "Twelve million records", detail: "PWS 3.1" }],
          },
          {
            turn_index: 0,
            persona_id: "technical_evaluator",
            concern_id: "technical_approach",
            rubric_row: "false_fact",
            support_value: -1,
            count: 1,
            evidence: [{ span: "Three waves", detail: "PWS 3.4" }],
          },
        ],
        limit_findings: [],
        clarifications: [],
        narrative: { scored: false, header: "Not scored", text: "Keep drilling details." },
      }),
    }),
  )

  await page.goto("/")
  await page.getByTestId("history-card").first().click()
  await expect(page.getByTestId("archive-view")).toBeVisible()
  await expect(page.getByText("False Fact x2")).toBeVisible()
  await expect(page.getByText("Max · from -4")).toBeVisible()
  await page
    .locator("details")
    .filter({ hasText: "Twelve million records" })
    .locator("summary")
    .click()
  await page.locator("details").filter({ hasText: "Three waves" }).locator("summary").click()
  await expect(page.getByText("“Twelve million records”", { exact: true })).toBeVisible()
  await expect(page.getByText("“Three waves”", { exact: true })).toBeVisible()
})
