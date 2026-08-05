import AxeBuilder from "@axe-core/playwright"
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
  expect(body.size).toBe("14px")
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
      moss100: read("--moss-100"),
      amber100: read("--amber-100"),
      scrim: read("--scrim"),
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
    moss100: "#E1E4DC",
    amber100: "#EFE5D9",
    scrim: "rgba(12, 30, 42, 0.40)",
  })
})

// The regression guard for the bug in spec §1.3: `bg-amber-600/10` compiled to
// no CSS rule at all, so the fill was invisible with no error anywhere.
test("tint utilities resolve to a real fill", async ({ page }) => {
  await page.goto("/?gallery")
  for (const token of ["moss-100", "amber-100"]) {
    const swatch = page.getByTestId(`gallery-swatch-${token}`)
    await expect(swatch).toBeVisible()
    const bg = await swatch.evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(bg).not.toBe("rgba(0, 0, 0, 0)")
    expect(bg).not.toBe("transparent")
  }
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

test("buttons carry through arbitrary attributes", async ({ page }) => {
  await page.goto("/?gallery")
  const titled = page.getByTestId("gallery-button-titled")
  await expect(titled).toHaveAttribute("title", "Passthrough")
  await expect(titled).toBeDisabled()
})

test("icon buttons render at both sizes", async ({ page }) => {
  await page.goto("/?gallery")
  for (const [size, px] of [
    ["sm", 28],
    ["md", 32],
  ] as const) {
    const box = await page.getByTestId(`gallery-icon-button-${size}`).boundingBox()
    expect(box?.height).toBeCloseTo(px, 0)
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

// The fill assertion matters as much as the height: a tone written as
// `bg-moss-600/10` renders invisibly and still passes a height check (spec §1.3).
test("every badge tone renders a resolved fill at 20px", async ({ page }) => {
  await page.goto("/?gallery")
  for (const tone of ["neutral", "live", "positive", "caution", "negative"]) {
    const badge = page.getByTestId(`gallery-badge-${tone}`)
    const box = await badge.boundingBox()
    expect(box?.height).toBeCloseTo(20, 0)
    const bg = await badge.evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(bg).not.toBe("rgba(0, 0, 0, 0)")
  }
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
  await expect(page.getByTestId("gallery-tag-default")).toHaveJSProperty("tagName", "SPAN")
  await expect(page.getByRole("button", { name: "Transition risk" })).toHaveCount(0)
})

const RUBRIC_ROWS = [
  "evidence_backed",
  "approach_cited",
  "unsubstantiated",
  "contradiction",
  "over_limit",
  "dodge",
  "false_fact",
  "red_line",
]

test("Textarea renders at 126px for five rows in both modes", async ({ page }) => {
  await page.goto("/?gallery")

  for (const mode of ["default", "inverse"]) {
    const field = page.getByTestId(`gallery-textarea-${mode}`)
    await expect(field).toBeVisible()
    const height = (await field.boundingBox())?.height ?? 0
    // rows=5 at 14px/1.43 plus `p-3` and the border resolves to ~126px; font
    // metrics vary by a fraction of a pixel between platforms.
    expect(Math.abs(height - 126), `${mode} height was ${height}`).toBeLessThanOrEqual(2)
  }
})

test("Textarea is controlled and reports its value upward", async ({ page }) => {
  await page.goto("/?gallery")
  const field = page.getByTestId("gallery-textarea-default")
  await field.fill("Twelve million records, three waves.")
  await expect(page.getByTestId("gallery-textarea-wordcount")).toHaveText("5 / 220 words")
})

// The fill assertion is the direct regression test for spec §1.3 —
// `unsubstantiated` rendered transparent because `bg-amber-600/10` compiled to
// nothing at all.
test("input and select share the control radius and token border", async ({ page }) => {
  await page.goto("/?gallery")
  for (const testid of ["gallery-input", "gallery-select"]) {
    const style = await page.getByTestId(testid).evaluate((el) => {
      const s = getComputedStyle(el)
      return { radius: s.borderTopLeftRadius, border: s.borderTopColor }
    })
    expect(style.radius).toBe("6px")
    expect(style.border).toBe("rgb(223, 213, 205)") // --border-subtle
  }
  const invalid = await page
    .getByTestId("gallery-input-invalid")
    .evaluate((el) => getComputedStyle(el).borderTopColor)
  expect(invalid).toBe("rgb(115, 29, 44)") // --crimson-700
})

test("sheet slides in from the right and closes on backdrop click", async ({ page }) => {
  await page.goto("/?gallery")
  await page.getByTestId("gallery-open-sheet").click()
  const panel = page.getByRole("dialog", { name: "Gallery sheet" })
  await expect(panel).toBeVisible()
  const [panelBox, viewport] = [await panel.boundingBox(), page.viewportSize()]
  expect(panelBox!.x + panelBox!.width).toBeCloseTo(viewport!.width, 0)
  await page.getByTestId("gallery-sheet-backdrop").click({ position: { x: 10, y: 10 } })
  await expect(panel).toBeHidden()
})

test("modal renders a scrim over a card and closes on Escape", async ({ page }) => {
  await page.goto("/?gallery")
  await page.getByTestId("gallery-open-modal").click()
  const scrim = page.getByTestId("gallery-modal-scrim")
  await expect(scrim).toBeVisible()
  expect(await scrim.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe(
    "rgba(12, 30, 42, 0.4)",
  )
  await expect(page.getByRole("dialog", { name: "Gallery modal" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(scrim).toBeHidden()
})

test("card renders the card radius, subtle border, and a shadow", async ({ page }) => {
  await page.goto("/?gallery")
  const card = page.getByTestId("gallery-card")
  const style = await card.evaluate((el) => {
    const s = getComputedStyle(el)
    return { radius: s.borderTopLeftRadius, bg: s.backgroundColor, shadow: s.boxShadow }
  })
  expect(style.radius).toBe("8px")
  expect(style.bg).toBe("rgb(255, 255, 255)")
  expect(style.shadow).not.toBe("none")

  const nested = page.getByTestId("gallery-card-nested")
  const nestedStyle = await nested.evaluate((el) => {
    const s = getComputedStyle(el)
    return { radius: s.borderTopLeftRadius, bg: s.backgroundColor, shadow: s.boxShadow }
  })
  expect(nestedStyle.radius).toBe("8px")
  expect(nestedStyle.bg).toBe("rgb(245, 241, 236)")
  expect(nestedStyle.shadow).toBe("none")
})

test("textarea forwards attributes and honors resize", async ({ page }) => {
  await page.goto("/?gallery")
  const box = page.getByTestId("gallery-textarea-resizable")
  await expect(box).toHaveAttribute("maxlength", "500")
  expect(await box.evaluate((el) => getComputedStyle(el).resize)).toBe("vertical")
})

test("micro caps tones resolve to distinct colors", async ({ page }) => {
  await page.goto("/?gallery")
  const read = (tone: string) =>
    page.getByTestId(`gallery-microcaps-${tone}`).evaluate((el) => getComputedStyle(el).color)
  expect(await read("muted")).not.toBe(await read("faint"))
})

test("every rubric row renders a chip with a resolved fill", async ({ page }) => {
  await page.goto("/?gallery")
  for (const row of RUBRIC_ROWS) {
    const chip = page.getByTestId(`gallery-verdict-${row}`)
    await expect(chip).toBeVisible()
    const bg = await chip.evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(bg).not.toBe("rgba(0, 0, 0, 0)")
  }
  const box = await page.getByTestId("gallery-verdict-red_line").boundingBox()
  expect(box?.height).toBeCloseTo(26, 0)
})

test("the gallery renders every token specimen", async ({ page }) => {
  await page.goto("/?gallery")

  await expect(page.getByTestId("gallery-swatch-crimson-700")).toBeVisible()
  await expect(page.getByTestId("gallery-swatch-sand-50")).toBeVisible()
  await expect(page.getByTestId("gallery-swatch-amber-600")).toBeVisible()

  // The three families are wired to real bundled faces, not fallbacks.
  await expect(page.getByTestId("gallery-type-display")).toHaveCSS("font-family", /Source Serif 4/)
  await expect(page.getByTestId("gallery-type-quote")).toHaveCSS("font-style", "italic")
  await expect(page.getByTestId("gallery-type-data")).toHaveCSS("font-family", /IBM Plex Mono/)

  await expect(page.getByTestId("gallery-radius-card")).toHaveCSS("border-radius", "8px")
  await expect(page.getByTestId("gallery-shadow-overlay")).not.toHaveCSS("box-shadow", "none")
})

// Strictly stronger than a11y-contrast.spec.ts, which scans one screen: the
// gallery renders every token pair and every primitive variant at once.
test("the whole gallery has no WCAG 2.1 AA contrast violations", async ({ page }) => {
  await page.goto("/?gallery")
  await expect(page.getByRole("heading", { name: "Airtight design system" })).toBeVisible()
  await expect(page.getByTestId("gallery-swatch-amber-600")).toBeVisible()

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(["region", "landmark-one-main"])
    .analyze()

  expect(results.violations).toEqual([])
})
