import { defineConfig, devices } from "@playwright/test"

// The tests run against an already-running stack (docker compose or local dev
// servers). `npm run e2e` boots the stack first; in CI the workflow does it.
const WEB_URL = process.env.E2E_WEB_URL ?? "http://localhost:5173"

// Chromium's fake media device auto-grants permission, emits a periodic tone,
// and exposes more than one named fake input — a moving meter and a real second
// option to select. Kept in its own project so the rest of the suite keeps
// exercising the normal permission path.
const MIC_SPEC = /mic-check\.spec\.ts/

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, testIgnore: MIC_SPEC },
    {
      name: "mic",
      testMatch: MIC_SPEC,
      use: {
        ...devices["Desktop Chrome"],
        permissions: ["microphone"],
        launchOptions: {
          args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        },
      },
    },
  ],
})
