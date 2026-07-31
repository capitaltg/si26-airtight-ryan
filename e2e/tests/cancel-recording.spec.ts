import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

// A 1-sample silent WAV. Stubbing spoken prompts keeps this spec off Polly and
// out of AWS credentials while the fake-media Chromium project records a real
// browser blob for the presenter answer.
const STUB_CLIP = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
const RAW = "so the the margin was uh twenty percent"
const HOLD_TO_TALK = /Hold this button/
const RECORDING = /Recording your answer/

// Complete because a kept take continues through the same scored-turn path as a
// normal voice answer.
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
  transcript: RAW,
  reply_audio: null,
  next_prompt_audio: null,
}

async function openVoiceMode(page: Page) {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByRole("button", { name: "Voice", exact: true }).click()
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
}

// Hold the button with the mouse, which is the path that takes pointer capture.
async function holdWithMouse(page: Page) {
  await page.getByRole("button", { name: HOLD_TO_TALK }).hover()
  await page.mouse.down()
  await expect(page.getByRole("button", { name: RECORDING })).toBeVisible()
  await page.waitForTimeout(1200)
}

async function recordAnswer(page: Page) {
  const button = page.getByRole("button", { name: HOLD_TO_TALK })
  await button.hover()
  await page.mouse.down()
  await page.waitForTimeout(1200)
  await page.mouse.up()
}

async function stubVoiceRoutes(page: Page, transcript: string, transcribeDelayMs = 0) {
  let transcribeCalls = 0
  let answerAudioCalls = 0

  await page.route("**/api/sessions/*/prompt_audio", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ audio: STUB_CLIP }),
    }),
  )
  await page.route("**/api/sessions/*/transcribe_audio", async (route) => {
    transcribeCalls += 1
    if (transcribeDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, transcribeDelayMs))
    }
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ transcript, duration_seconds: 72.5 }),
    })
  })
  await page.route("**/api/sessions/*/answer_audio", (route) => {
    answerAudioCalls += 1
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(SCORED_RESPONSE),
    })
  })

  return {
    transcribeCalls: () => transcribeCalls,
    answerAudioCalls: () => answerAudioCalls,
  }
}

test("Escape mid-recording asks before it throws the take away", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)
  await expect(page.getByTestId("prompt-intro")).toHaveCount(1)
  const promptText = await page.getByTestId("prompt-intro").textContent()

  await holdWithMouse(page)
  await page.keyboard.press("Escape")

  const dialog = page.getByTestId("discard-recording")
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText("Discard this recording?")
  await expect(page.getByTestId("discard-recording-keep")).toHaveText("Use recording")
  await page.mouse.up()

  // The mic is already released and the take is held in memory: nothing has
  // been sent anywhere yet.
  await page.waitForTimeout(500)
  await expect.poll(routes.transcribeCalls).toBe(0)
  expect(await page.getByTestId("prompt-intro").textContent()).toBe(promptText)
})

test("Discard take returns to hold-to-talk with nothing sent", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)

  await holdWithMouse(page)
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("discard-recording")).toBeVisible()
  await page.mouse.up()
  await page.getByTestId("discard-recording-discard").click()

  await expect(page.getByTestId("discard-recording")).toHaveCount(0)
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
  await expect(page.getByTestId("voice-review")).toHaveCount(0)
  await expect.poll(routes.transcribeCalls).toBe(0)
  await expect.poll(routes.answerAudioCalls).toBe(0)
})

test("Use recording falls through to the normal review card", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)

  await holdWithMouse(page)
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("discard-recording")).toBeVisible()
  await page.mouse.up()
  await page.getByTestId("discard-recording-keep").click()

  await expect(page.getByTestId("voice-review")).toBeVisible()
  await expect(page.getByTestId("voice-review-text")).toHaveValue(RAW)
  await expect.poll(routes.transcribeCalls).toBe(1)
})

test("the confirm dialog blocks the mode toggle, the mic check, and push-to-talk", async ({
  page,
}) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)

  await holdWithMouse(page)
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("discard-recording")).toBeVisible()
  await page.mouse.up()

  await expect(page.getByRole("button", { name: "Text", exact: true })).toBeDisabled()
  await expect(page.getByRole("button", { name: "Voice", exact: true })).toBeDisabled()
  await expect(page.getByRole("button", { name: "Mic check" })).toBeDisabled()

  await page.locator("body").press("Space")
  await page.waitForTimeout(500)
  await expect(page.getByTestId("discard-recording")).toBeVisible()
  await expect(page.getByRole("button", { name: RECORDING })).toHaveCount(0)
  await expect.poll(routes.transcribeCalls).toBe(0)
})

test("the Cancel button reaches a Space push-to-talk hold", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW)
  await openVoiceMode(page)

  // A pointer hold captures the pointer on the talk button, so the Cancel
  // button is only clickable during a keyboard hold. That is the case this
  // covers; Escape covers the pointer case.
  await page.keyboard.down("Space")
  await expect(page.getByRole("button", { name: RECORDING })).toBeVisible()
  await page.waitForTimeout(1200)
  await page.getByTestId("cancel-recording").click()
  await page.keyboard.up("Space")

  await expect(page.getByTestId("discard-recording")).toBeVisible()
  await page.getByTestId("discard-recording-discard").click()
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
  await expect.poll(routes.transcribeCalls).toBe(0)
})

test("Keep waiting leaves the transcription running", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW, 3000)
  await openVoiceMode(page)

  await recordAnswer(page)
  await expect(page.getByRole("button", { name: /Transcribing/ })).toBeVisible()
  await page.getByTestId("cancel-recording").click()

  await expect(page.getByTestId("discard-recording-keep")).toHaveText("Keep waiting")
  await page.getByTestId("discard-recording-keep").click()

  await expect(page.getByTestId("discard-recording")).toHaveCount(0)
  await expect(page.getByTestId("voice-review")).toBeVisible()
  await expect(page.getByTestId("voice-review-text")).toHaveValue(RAW)
  await expect.poll(routes.transcribeCalls).toBe(1)
})

test("Discard take during transcription drops the take without an error", async ({ page }) => {
  const routes = await stubVoiceRoutes(page, RAW, 3000)
  await openVoiceMode(page)

  await recordAnswer(page)
  await expect(page.getByRole("button", { name: /Transcribing/ })).toBeVisible()
  await page.getByTestId("cancel-recording").click()
  await page.getByTestId("discard-recording-discard").click()

  await expect(page.getByTestId("discard-recording")).toHaveCount(0)
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
  await expect(page.getByTestId("voice-review")).toHaveCount(0)

  // The regression guard for a missing transcribeAudio.reset(): without it the
  // aborted fetch renders as "The user aborted a request." next to the talk
  // button. Waits past the stub's delay so a late response cannot sneak a
  // review card in behind the assertion.
  await page.waitForTimeout(3500)
  await expect(page.getByText(/aborted/i)).toHaveCount(0)
  await expect(page.locator(".text-red-700")).toHaveCount(0)
  await expect(page.getByTestId("voice-review")).toHaveCount(0)
  await expect.poll(routes.answerAudioCalls).toBe(0)
})

test("Discard take wins if transcription completes behind its confirmation dialog", async ({
  page,
}) => {
  const routes = await stubVoiceRoutes(page, RAW, 3000)
  await openVoiceMode(page)

  await recordAnswer(page)
  await expect(page.getByRole("button", { name: /Transcribing/ })).toBeVisible()
  await page.getByTestId("cancel-recording").click()
  await expect(page.getByTestId("discard-recording")).toBeVisible()

  // The response can settle after the confirmation opens but before the
  // presenter chooses. The still-open dialog's discard choice must override
  // that late success instead of leaving the review card behind.
  await expect(page.getByTestId("voice-review")).toBeVisible()
  await page.getByTestId("discard-recording-discard").click()

  await expect(page.getByTestId("discard-recording")).toHaveCount(0)
  await expect(page.getByTestId("voice-review")).toHaveCount(0)
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
  await expect.poll(routes.answerAudioCalls).toBe(0)
})
