import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

// A 1-sample silent WAV. Stubbing spoken prompts keeps this test independent
// from Polly and AWS credentials while the fake-media Chromium project records
// a real browser blob for the presenter answer.
const STUB_CLIP = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
const RAW = "so the the margin was uh twenty percent"
const EDITED = "The margin was 20 percent."
const HOLD_TO_TALK = /Hold this button/

// The response must be complete because the review confirmation continues
// through the same scored-turn rendering path as a normal voice answer.
const SCORED_RESPONSE = {
  reply: "That margin is now clear.",
  rationale: "The answer gives a concrete margin.",
  persona_id: "technical_evaluator",
  concern_id: "technical_approach",
  concern_status: "satisfied",
  support_delta: 2,
  matched_rows: ["backed_specific"],
  meter: 52,
  capped: false,
  limit: null,
  meters: [
    { persona_id: "technical_evaluator", support: 52, capped: false },
    { persona_id: "contracting_officer", support: 50, capped: false },
    { persona_id: "program_rep", support: 50, capped: false },
  ],
  next_prompt: {
    persona_id: "technical_evaluator",
    display_name: "Dana",
    concern_id: "key_personnel",
    prompt: "Name the key personnel and tell me what they have actually delivered.",
    is_follow_up: false,
    intro: null,
  },
  done: false,
  transcript: EDITED,
  reply_audio: null,
  next_prompt_audio: null,
}

async function openVoiceMode(page: Page) {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByRole("button", { name: "Voice", exact: true }).click()
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
}

async function recordAnswer(page: Page) {
  const button = page.getByRole("button", { name: HOLD_TO_TALK })
  await button.hover()
  await page.mouse.down()
  await page.waitForTimeout(1200)
  await page.mouse.up()
}

async function stubVoiceRoutes(page: Page, transcript: string) {
  let transcribeCalls = 0
  let submittedMultipart = ""

  await page.route("**/api/sessions/*/prompt_audio", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ audio: STUB_CLIP }),
    }),
  )
  await page.route("**/api/sessions/*/transcribe_audio", (route) => {
    transcribeCalls += 1
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ transcript, duration_seconds: 72.5 }),
    })
  })
  await page.route("**/api/sessions/*/answer_audio", (route) => {
    submittedMultipart = route.request().postData() ?? ""
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(SCORED_RESPONSE),
    })
  })

  return {
    transcribeCalls: () => transcribeCalls,
    submittedMultipart: () => submittedMultipart,
  }
}

test("a presenter edits the reviewed transcript before the recording is scored", async ({
  page,
}) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)

  await recordAnswer(page)

  const review = page.getByTestId("voice-review")
  await expect(review).toBeVisible()
  await expect(page.getByTestId("voice-review-text")).toHaveValue(RAW)
  await expect(page.getByTestId("voice-review-duration")).toContainText("72.5")

  await page.getByTestId("voice-review-text").fill(EDITED)
  await review.getByRole("button", { name: "Submit" }).click()

  await expect(review).toHaveCount(0)
  await expect(page.getByText(EDITED, { exact: true })).toBeVisible()
  expect(routes.submittedMultipart()).toContain('name="audio"; filename="answer.webm"')
  expect(routes.submittedMultipart()).toContain('name="raw_transcript"')
  expect(routes.submittedMultipart()).toContain(RAW)
  expect(routes.submittedMultipart()).toContain('name="answer"')
  expect(routes.submittedMultipart()).toContain(EDITED)

  const original = page.getByTestId("original-transcription")
  await expect(original).not.toHaveAttribute("open", "")
  await original.locator("summary").click()
  await expect(original).toHaveAttribute("open", "")
  await expect(original).toContainText(RAW)
})

test("a blank automatic transcript remains editable but cannot be submitted empty", async ({
  page,
}) => {
  await stubVoiceRoutes(page, "")
  await openVoiceMode(page)

  await recordAnswer(page)

  const review = page.getByTestId("voice-review")
  await expect(review).toBeVisible()
  await expect(page.getByTestId("voice-review-text")).toHaveValue("")
  await expect(review).toContainText("Nothing was heard. Type what you said.")
  await expect(review.getByRole("button", { name: "Submit" })).toBeDisabled()
})

test("review blocks mode controls and global push-to-talk", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)

  await recordAnswer(page)

  await expect(page.getByTestId("voice-review")).toBeVisible()
  await expect(page.getByRole("button", { name: "Text", exact: true })).toBeDisabled()
  await expect(page.getByRole("button", { name: "Mic check" })).toBeDisabled()

  await page.locator("body").press("Space")
  await page.waitForTimeout(500)
  await expect.poll(routes.transcribeCalls).toBe(1)
})
