import { expect, test } from "@playwright/test"

// A 1-sample silent WAV, base64 (the same clip audio.ts primes with). Stubbing
// the response keeps the test off real Polly and out of AWS credentials.
const STUB_CLIP = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="

// The hold-to-talk button's aria-label when idle (Rehearsal.tsx) — proof that
// voice mode actually opened.
const HOLD_TO_TALK = /Hold this button/

test("switching to voice requests the spoken prompt", async ({ page }) => {
  let calls = 0
  await page.route("**/api/sessions/*/prompt_audio", (route) => {
    calls += 1
    return route.fulfill({
      status: 200,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ audio: STUB_CLIP }),
    })
  })

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await expect(page.getByTestId("prompt-intro")).toHaveCount(1)

  await page.getByRole("button", { name: "Voice", exact: true }).click()
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
  await expect.poll(() => calls).toBe(1)

  // Clicking Voice while already in voice mode is not a transition, so it must
  // not re-request the clip.
  await page.getByRole("button", { name: "Voice", exact: true }).click()
  await expect.poll(() => calls).toBe(1)

  // Out to text and back in is a real transition: a second clip.
  await page.getByRole("button", { name: "Text", exact: true }).click()
  await expect(page.getByPlaceholder("Your answer…")).toBeVisible()
  await page.getByRole("button", { name: "Voice", exact: true }).click()
  await expect.poll(() => calls).toBe(2)
})

test("a failed prompt clip does not block voice mode", async ({ page }) => {
  await page.route("**/api/sessions/*/prompt_audio", (route) =>
    route.fulfill({
      status: 500,
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ detail: "polly is unavailable" }),
    }),
  )

  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByRole("button", { name: "Voice", exact: true }).click()

  // Voice mode is open and the presenter sees no error: the prompt and intro
  // are on screen to read.
  await expect(page.getByRole("button", { name: HOLD_TO_TALK })).toBeVisible()
  await expect(page.getByText("polly is unavailable")).toHaveCount(0)
})
