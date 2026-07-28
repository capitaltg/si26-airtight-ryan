import { expect, test } from "@playwright/test"

// A distinctive slice of the authored intro in
// server/app/content/store/personas/technical_evaluator.md. Kept as a substring
// so rewording the rest of the sentence doesn't break the test.
const DANA_INTRO = "senior technical evaluator on the source-selection board"

// The pipeline's SSE shape: stage frames, then one terminal result frame
// (server/app/api/sessions.py's /answer/stream).
function sseBody(result: unknown): string {
  return (
    `data: ${JSON.stringify({ stage: "extracting" })}\n\n` +
    `data: ${JSON.stringify({ stage: "scoring" })}\n\n` +
    `data: ${JSON.stringify({ stage: "reacting" })}\n\n` +
    `data: ${JSON.stringify({ result })}\n\n`
  )
}

// A scored turn on Dana's opening concern whose next prompt is Dana again — so
// the incoming prompt carries no intro.
const NEXT_WITHOUT_INTRO = {
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
    persona_id: "technical_evaluator",
    concern_id: "key_personnel",
    prompt: "Name the key personnel and tell me what they have actually delivered.",
    is_follow_up: false,
    intro: null,
  },
  done: false,
}

test("the opening prompt introduces the evaluator", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()

  await expect(page.getByTestId("prompt-intro")).toHaveCount(1)
  await expect(page.getByTestId("prompt-intro")).toContainText(DANA_INTRO)
})

test("an answered turn keeps its intro and the next prompt shows none", async ({ page }) => {
  await page.route("**/api/sessions/*/answer/stream", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: sseBody(NEXT_WITHOUT_INTRO),
    }),
  )

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await expect(page.getByTestId("prompt-intro")).toContainText(DANA_INTRO)

  await page.getByPlaceholder("Your answer…").fill("Three named services on a FedRAMP host.")
  await page.getByRole("button", { name: "Submit" }).click()

  // The next prompt is live...
  await expect(page.getByText("Name the key personnel")).toBeVisible()
  // ...and the only intro left on the page is the one on the completed turn in
  // the scrollback, which keeps the intro it was displayed with.
  await expect(page.getByTestId("prompt-intro")).toHaveCount(1)
  await expect(page.getByTestId("prompt-intro")).toContainText(DANA_INTRO)
  await expect(page.getByText("Concrete enough. Noted.")).toBeVisible()
})
