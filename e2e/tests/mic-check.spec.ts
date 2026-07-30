import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

// This file runs only under the `mic` project (playwright.config.ts), which
// launches Chromium with fake media devices: permission is auto-granted, the
// fake input emits a periodic tone, and more than one fake input is exposed.

// A 1-sample silent WAV, base64. The stack boots without AWS credentials, so
// the spoken-prompt route is stubbed the same way voice-prompt-audio.spec.ts
// does it.
const STUB_CLIP = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="

const HOLD_TO_TALK = /Hold this button/
const RECORDING = /Recording your answer/

async function openLandingPanel(page: Page) {
  await page.getByTestId("mic-check-toggle").click()
  // The `mic` project grants microphone permission up front, so labels are
  // normally already visible almost immediately; click through the prompt in
  // the rare case this browser still withholds them. A plain count-then-click
  // races the panel's own re-render — permission resolves fast enough that
  // the button can vanish between the count and the click, which Playwright
  // reports as a timeout ("element was detached from the DOM") rather than a
  // clean no-op. A short-timeout best-effort click absorbs that race: if the
  // button is gone before the click lands, labels were already visible and
  // there's nothing to do.
  const allow = page.getByRole("button", { name: "Allow microphone access" })
  await allow.click({ timeout: 2_000 }).catch(() => {})
  await expect(page.getByTestId("mic-input-select")).toBeVisible()
}

test("the level meter reports sound from the fake input", async ({ page }) => {
  await page.goto("/")
  await openLandingPanel(page)

  const options = page.getByTestId("mic-input-select").locator("option")
  // "System default" plus at least two fake inputs.
  await expect.poll(() => options.count()).toBeGreaterThan(2)

  await expect(page.getByTestId("mic-level-status")).toHaveText("Microphone is picking up sound", {
    timeout: 15_000,
  })
})

test("the selected input survives a reload", async ({ page }) => {
  await page.goto("/")
  await openLandingPanel(page)

  // Chromium's fake device flags only give a stable id ("default") to the
  // default fake input; the extra named inputs ("Fake Audio Input 1", "Fake
  // Audio Input 2") get a fresh random deviceId every navigation, which would
  // make this test fail on the id itself rather than on persistence. "default"
  // is still a real, non-empty choice distinct from "System default" (value
  // ""), so selecting it still exercises the same localStorage round-trip.
  const select = page.getByTestId("mic-input-select")
  const stableInput = await select.locator('option[value="default"]').getAttribute("value")
  expect(stableInput).toBe("default")
  await select.selectOption("default")

  await page.reload()
  await openLandingPanel(page)
  await expect(page.getByTestId("mic-input-select")).toHaveValue("default")
})

test("a test recording plays back", async ({ page }) => {
  await page.goto("/")
  await openLandingPanel(page)

  await page.getByRole("button", { name: "Record a test clip" }).click()
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible()
  // Roughly a second of the fake device's tone, well under the 5s auto-stop.
  await page.waitForTimeout(1200)
  await page.getByRole("button", { name: "Stop" }).click()

  const clip = page.getByTestId("mic-test-clip")
  await expect(clip).toBeVisible()
  await expect.poll(async () => (await clip.getAttribute("src")) ?? "").toContain("blob:")
})

test("playing the test sound surfaces no error", async ({ page }) => {
  await page.goto("/")
  await openLandingPanel(page)

  await page.getByRole("button", { name: "Play test sound" }).click()
  // The tone itself is not assertable from Playwright, so the assertion is the
  // absence of a failure path.
  await page.waitForTimeout(1000)
  await expect(page.getByTestId("mic-error")).toHaveCount(0)
})

test("the in-session panel blocks push-to-talk", async ({ page }) => {
  await page.route("**/api/sessions/*/prompt_audio", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ audio: STUB_CLIP }),
    }),
  )

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByRole("button", { name: "Voice", exact: true }).click()
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()

  await page.getByRole("button", { name: "Mic check" }).click()
  await expect(page.getByRole("dialog", { name: "Mic check" })).toBeVisible()

  await page.keyboard.down("Space")
  await page.waitForTimeout(500)
  await page.keyboard.up("Space")
  // The hold-to-talk button behind the modal never entered its recording state.
  await expect(page.getByRole("button", { name: RECORDING })).toHaveCount(0)

  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog", { name: "Mic check" })).toHaveCount(0)
})
