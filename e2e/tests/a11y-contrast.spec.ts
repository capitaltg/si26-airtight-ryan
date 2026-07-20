import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"

// WCAG 2.1 AA color-contrast check. axe-core's `color-contrast` rule enforces
// the 4.5:1 (normal text) / 3:1 (large text) ratio from success criterion
// 1.4.3. Federal software falls under Section 508, which points at WCAG 2.0/2.1
// AA, so this guards the whole UI against low-contrast regressions as it grows.
//
// Scoped to contrast only for now. Drop `.withRules` and use
// `.withTags(["wcag2a", "wcag2aa", "wcag21aa"])` to widen to a full AA audit.
test("home page has no WCAG 2.1 AA contrast violations", async ({ page }) => {
  await page.goto("/")
  // Wait for steady state so transient loading text is not what gets scanned.
  await expect(page.getByRole("heading", { name: "Airtight" })).toBeVisible()

  const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze()

  expect(results.violations).toEqual([])
})
