import { expect, test } from "@playwright/test"

// SP1 lands only the token layer and the primitives; it restyles no screen.
// These tests therefore assert the token layer directly — on `body` for the
// page ground and type, and on the dev-only gallery for everything else.

test("the page ground and body type come from the token layer", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Airtight" })).toBeVisible()

  const body = await page.evaluate(() => {
    const cs = getComputedStyle(document.body)
    return {
      background: cs.backgroundColor,
      family: cs.fontFamily,
      size: cs.fontSize,
      color: cs.color,
    }
  })

  expect(body.background).toBe("rgb(245, 241, 236)") // --sand-50, never pure white
  expect(body.family).toContain("Public Sans")
  expect(body.size).toBe("15px")
  expect(body.color).toBe("rgb(42, 59, 71)") // --text-body
})

test("the raw palette anchors resolve to their handoff values", async ({ page }) => {
  await page.goto("/")

  const tokens = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement)
    const read = (name: string) => cs.getPropertyValue(name).trim()
    return {
      crimson: read("--crimson-700"),
      navy: read("--navy-800"),
      teal: read("--teal-600"),
      taupe: read("--taupe-600"),
      sand50: read("--sand-50"),
      moss: read("--moss-600"),
      amber: read("--amber-600"),
    }
  })

  expect(tokens).toEqual({
    crimson: "#731D2C",
    navy: "#122E40",
    teal: "#1E4E59",
    taupe: "#73675D",
    sand50: "#F5F1EC",
    moss: "#2F6B4F",
    amber: "#B4762A",
  })
})

test("the gallery is reachable and renders icons and micro-caps labels", async ({ page }) => {
  await page.goto("/?gallery")
  await expect(page.getByRole("heading", { name: "Airtight design system" })).toBeVisible()

  // Icon renders a real inline SVG at the requested size.
  const icon = page.getByTestId("gallery-icon-gavel").locator("svg")
  await expect(icon).toBeVisible()
  const box = await icon.boundingBox()
  expect(box?.width).toBe(17)
  expect(box?.height).toBe(17)

  // MicroCaps carries the 0.09em tracking that marks it in the handoff.
  const caps = page.getByTestId("gallery-microcaps")
  await expect(caps).toHaveText("Briefing topic")
  const capsStyle = await caps.evaluate((el) => {
    const cs = getComputedStyle(el)
    return {
      size: cs.fontSize,
      weight: cs.fontWeight,
      tracking: cs.letterSpacing,
      transform: cs.textTransform,
    }
  })
  expect(capsStyle).toEqual({
    size: "12px",
    weight: "600",
    tracking: "1.08px", // 0.09em at 12px
    transform: "uppercase",
  })
})

const BUTTON_HEIGHTS = { sm: 30, md: 38, lg: 48 } as const
const BUTTON_VARIANTS = ["primary", "secondary", "ghost", "inverse", "danger"] as const

test("every Button variant and size renders at its handoff height", async ({ page }) => {
  await page.goto("/?gallery")
  await expect(page.getByRole("heading", { name: "Airtight design system" })).toBeVisible()

  for (const variant of BUTTON_VARIANTS) {
    for (const [size, height] of Object.entries(BUTTON_HEIGHTS)) {
      const button = page.getByTestId(`gallery-button-${variant}-${size}`)
      await expect(button).toBeVisible()
      const box = await button.boundingBox()
      expect(box?.height, `${variant}/${size}`).toBe(height)
    }
  }
})

test("IconButton is square and carries an accessible name", async ({ page }) => {
  await page.goto("/?gallery")
  const close = page.getByRole("button", { name: "Close" })
  await expect(close).toBeVisible()
  const box = await close.boundingBox()
  expect(box?.width).toBe(32)
  expect(box?.height).toBe(32)
})
