import { expect, test } from "@playwright/test"

test("text answer shows disclosed live word count", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: "Start rehearsal" }).click()
  await page.getByPlaceholder("Your answer…").fill("one two three")

  await expect(page.getByText("3 / 300 words")).toBeVisible()
})
