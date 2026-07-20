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

test("web app loads and shows API health as ok", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Airtight" })).toBeVisible()
  // App.tsx fetches /api/health through the proxy and renders the status text.
  await expect(page.getByText("ok", { exact: true })).toBeVisible()
})
