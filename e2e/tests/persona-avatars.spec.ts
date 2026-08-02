import { expect, test } from "@playwright/test"

function sseBody(result: unknown): string {
  return (
    `data: ${JSON.stringify({ stage: "extracting" })}\n\n` +
    `data: ${JSON.stringify({ stage: "scoring" })}\n\n` +
    `data: ${JSON.stringify({ stage: "reacting" })}\n\n` +
    `data: ${JSON.stringify({ result })}\n\n`
  )
}

const HANDOFF_TO_MARCUS = {
  reply: "Concrete enough. Noted.",
  rationale: "Backed specifics on all three sub-questions.",
  persona_id: "technical_evaluator",
  concern_id: "technical_approach",
  concern_status: "satisfied",
  support_delta: 2,
  matched_rows: ["backed_specific"],
  meter: 52,
  capped: false,
  meters: [
    { persona_id: "technical_evaluator", support: 52, capped: false },
    { persona_id: "contracting_officer", support: 50, capped: false },
    { persona_id: "program_rep", support: 50, capped: false },
  ],
  next_prompt: {
    persona_id: "contracting_officer",
    concern_id: "price_realism",
    prompt: "Walk me through how this price is realistic.",
    is_follow_up: false,
    intro: null,
  },
  done: false,
}

const AVATAR = "[data-testid='persona-avatar']"

test("the opening prompt renders a locally generated persona avatar", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()

  const avatar = page.locator(AVATAR).first()
  await expect(avatar).toBeVisible()
  await expect(avatar).toHaveAttribute("src", /^data:image\/svg\+xml/)
  await expect(avatar).toHaveAttribute("data-persona", "technical_evaluator")
})

test("every avatar is decorative", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await expect(page.locator(AVATAR).first()).toBeVisible()

  const avatars = page.locator(AVATAR)
  expect(
    await avatars.evaluateAll((els) =>
      els.every((avatar) => avatar.getAttribute("aria-hidden") === "true" && avatar.alt === ""),
    ),
  ).toBe(true)
})

test("one persona keeps one avatar; different personas differ", async ({ page }) => {
  await page.route("**/api/sessions/*/answer/stream", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: sseBody(HANDOFF_TO_MARCUS),
    }),
  )

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByPlaceholder("Your answer…").fill("Three named services on a FedRAMP host.")
  await page.getByRole("button", { name: "Submit" }).click()
  await expect(page.getByText("Walk me through how this price is realistic.")).toBeVisible()

  const dana = page.locator(`${AVATAR}[data-persona='technical_evaluator']`)
  expect(await dana.count()).toBeGreaterThan(1)
  const danaSrcs = await dana.evaluateAll((els) => els.map((e) => (e as HTMLImageElement).src))
  expect(new Set(danaSrcs).size).toBe(1)

  const marcusSrc = await page
    .locator(`${AVATAR}[data-persona='contracting_officer']`)
    .first()
    .getAttribute("src")
  expect(marcusSrc).not.toBe(danaSrcs[0])
})

const SESSION_ID = "22222222-2222-2222-2222-222222222222"

test("the after-action report carries avatars on every persona line", async ({ page }) => {
  await page.route("**/api/sessions/history", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify([
        {
          id: SESSION_ID,
          status: "complete",
          created_at: "2026-08-01T12:00:00Z",
          archived_at: "2026-08-01T12:40:00Z",
          turn_count: 1,
          meters: [{ persona_id: "technical_evaluator", support: 48, capped: false }],
          concerns_satisfied: 1,
          concerns_total: 8,
        },
      ]),
    }),
  )
  await page.route(`**/api/sessions/${SESSION_ID}/transcript`, (route) =>
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
            raw_support_delta: -2,
            matched_rows: ["false_fact"],
            row_counts: { false_fact: 1 },
            capped: false,
            scored: true,
            transcript: null,
            limit: null,
          },
        ],
      }),
    }),
  )
  await page.route(`**/api/sessions/${SESSION_ID}/report`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        session_id: SESSION_ID,
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
        personas: [{ persona_id: "technical_evaluator", support: 48, capped: false }],
        coverage_counts: { full: 0, partial: 0, none: 0 },
        dodge_counts_by_type: {},
        contradiction_count: 0,
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
        ],
        limit_findings: [
          {
            turn_index: 0,
            persona_id: "contracting_officer",
            concern_id: "price_realism",
            kind: "text_words",
            measured: 210,
            limit_threshold: 180,
            penalty: -1,
          },
        ],
        clarifications: [
          {
            persona_id: "program_rep",
            concern_id: "transition",
            question: "Do you mean the phase-in window?",
            reply: "Yes - the first thirty days.",
          },
        ],
        narrative: { scored: false, header: "Not scored", text: "Keep drilling details." },
      }),
    }),
  )

  await page.goto("/")
  await page.getByTestId("history-card").first().click()
  await expect(page.getByTestId("archive-view")).toBeVisible()

  await expect(page.locator(`${AVATAR}[data-persona='technical_evaluator']`).first()).toBeVisible()
  await expect(page.locator(`${AVATAR}[data-persona='contracting_officer']`).first()).toBeVisible()
  await expect(page.locator(`${AVATAR}[data-persona='program_rep']`).first()).toBeVisible()
})

test("a persona's avatar survives a reload", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  const first = await page
    .locator(`${AVATAR}[data-persona='technical_evaluator']`)
    .first()
    .getAttribute("src")

  await page.reload()
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  const second = await page
    .locator(`${AVATAR}[data-persona='technical_evaluator']`)
    .first()
    .getAttribute("src")

  expect(second).toBe(first)
})
