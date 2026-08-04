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

test("Badge renders both tones at 20px and only the live tone animates", async ({ page }) => {
  await page.goto("/?gallery")

  for (const tone of ["live", "neutral"]) {
    const badge = page.getByTestId(`gallery-badge-${tone}`)
    await expect(badge).toBeVisible()
    expect((await badge.boundingBox())?.height, tone).toBe(20)
  }

  const liveDot = page.getByTestId("gallery-badge-live").locator("span").first()
  await expect(liveDot).toHaveCSS("animation-name", "livePulse")
  await expect(liveDot).toHaveCSS("animation-duration", "1.4s")
  await expect(liveDot).toHaveCSS("animation-iteration-count", "infinite")

  const neutral = page.getByTestId("gallery-badge-neutral")
  await expect(neutral).toHaveCSS("animation-name", "none")
})

test("Tag renders every state at 24px and stays clickable when given onClick", async ({ page }) => {
  await page.goto("/?gallery")

  for (const state of ["default", "muted", "selected", "icon"]) {
    const tag = page.getByTestId(`gallery-tag-${state}`)
    await expect(tag).toBeVisible()
    expect((await tag.boundingBox())?.height, state).toBe(24)
  }

  // A Tag with onClick is a real button; one without is not focusable.
  await expect(page.getByTestId("gallery-tag-selected")).toHaveRole("button")
  await expect(page.getByTestId("gallery-tag-default")).toHaveRole("generic")
})

const VERDICTS = ["evidenceBacked", "approachCited", "unsubstantiated", "dodge", "redLine"] as const

test("Textarea renders at 148px for five rows in both modes", async ({ page }) => {
  await page.goto("/?gallery")

  for (const mode of ["default", "inverse"]) {
    const field = page.getByTestId(`gallery-textarea-${mode}`)
    await expect(field).toBeVisible()
    const height = (await field.boundingBox())?.height ?? 0
    // rows=5 at 15px/1.65 plus 12px padding resolves to ~148px; font metrics
    // vary by a fraction of a pixel between platforms.
    expect(Math.abs(height - 148), `${mode} height was ${height}`).toBeLessThanOrEqual(2)
  }
})

test("Textarea is controlled and reports its value upward", async ({ page }) => {
  await page.goto("/?gallery")
  const field = page.getByTestId("gallery-textarea-default")
  await field.fill("Twelve million records, three waves.")
  await expect(page.getByTestId("gallery-textarea-wordcount")).toHaveText("5 / 220 words")
})

test("every VerdictChip renders at 26px at size lg", async ({ page }) => {
  await page.goto("/?gallery")

  for (const verdict of VERDICTS) {
    const chip = page.getByTestId(`gallery-verdict-${verdict}`)
    await expect(chip).toBeVisible()
    expect((await chip.boundingBox())?.height, verdict).toBe(26)
  }
})
