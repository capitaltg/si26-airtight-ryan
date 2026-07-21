import { expect, test } from "@playwright/test"

// Direct API check does not go through the browser, so it can target the API
// port straight. The web check exercises the full path: browser -> Vite proxy
// -> FastAPI.
const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000"

test("API /health returns ok", async ({ request }) => {
  const res = await request.get(`${API_URL}/health`)
  expect(res.ok()).toBeTruthy()
  expect(await res.json()).toEqual({ status: "ok" })
})

test("web app loads and starts a rehearsal through the API proxy", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Airtight" })).toBeVisible()
  // Starting a session exercises the full path: browser -> Vite proxy -> FastAPI
  // (POST /api/sessions). The active-rehearsal view only renders on success, so
  // its "How you're scored" control being visible proves the proxy round-trip.
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await expect(page.getByRole("button", { name: "How you're scored" })).toBeVisible()
})
