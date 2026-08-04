import { useState } from "react"
import type { ReactNode } from "react"

import { Badge } from "./ui/Badge"
import { Button, type ButtonSize, type ButtonVariant } from "./ui/Button"
import { Card } from "./ui/Card"
import { Icon, ICON_NAMES } from "./ui/Icon"
import { IconButton } from "./ui/IconButton"
import { Input } from "./ui/Input"
import { MicroCaps } from "./ui/MicroCaps"
import { Modal } from "./ui/Modal"
import { Select } from "./ui/Select"
import { Sheet } from "./ui/Sheet"
import { Tag } from "./ui/Tag"
import { Textarea } from "./ui/Textarea"
import { RUBRIC_ROWS, VerdictChip } from "./ui/VerdictChip"

// Development-only surface, and the permanent one: the repo has no Storybook, so
// this is where a token or primitive is checked in isolation before or after a
// screen consumes it. Mounted from App.tsx behind `import.meta.env.DEV`.

const BUTTON_VARIANTS: ButtonVariant[] = ["primary", "secondary", "ghost", "inverse", "danger"]
const BUTTON_SIZES: ButtonSize[] = ["sm", "md", "lg"]

const SWATCHES: { token: string; className: string }[] = [
  { token: "crimson-700", className: "bg-crimson-700" },
  { token: "crimson-600", className: "bg-crimson-600" },
  { token: "crimson-100", className: "bg-crimson-100" },
  { token: "navy-900", className: "bg-navy-900" },
  { token: "navy-800", className: "bg-navy-800" },
  { token: "teal-600", className: "bg-teal-600" },
  { token: "taupe-600", className: "bg-taupe-600" },
  { token: "sand-300", className: "bg-sand-300" },
  { token: "sand-200", className: "bg-sand-200" },
  { token: "sand-50", className: "bg-sand-50" },
  { token: "moss-600", className: "bg-moss-600" },
  { token: "amber-600", className: "bg-amber-600" },
  // The two tints. No `scrim` swatch: a 40%-alpha fill over the gallery's own
  // ground reports a blended color and tells you nothing — Modal and Sheet
  // exercise it instead.
  { token: "moss-100", className: "bg-moss-100" },
  { token: "amber-100", className: "bg-amber-100" },
]

const TEXT_TOKENS = [
  "text-body",
  "text-strong",
  "text-muted",
  "text-faint",
  "text-link",
  "text-link-hover",
] as const

const RADII = ["chip", "control", "block", "card", "panel"] as const
const SHADOWS = ["xs", "sm", "md", "lg", "overlay"] as const

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <MicroCaps as="h2">{title}</MicroCaps>
      <div className="flex flex-col gap-6">{children}</div>
    </section>
  )
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="font-data text-body-sm text-text-faint">{label}</div>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  )
}

function TextareaSpecimen() {
  const [draft, setDraft] = useState("")
  const words = draft.trim() === "" ? 0 : draft.trim().split(/\s+/).length

  return (
    <Section title="Input and verdicts">
      <div className="grid gap-6 md:grid-cols-2">
        <Textarea
          value={draft}
          onChange={setDraft}
          placeholder="Your answer…"
          aria-label="Answer, default mode"
          data-testid="gallery-textarea-default"
          hint={<span data-testid="gallery-textarea-wordcount">{words} / 220 words</span>}
        />
        <div className="rounded-card bg-navy-800 p-4">
          <Textarea
            inverse
            value={draft}
            onChange={setDraft}
            placeholder="Your answer…"
            aria-label="Answer, inverse mode"
            data-testid="gallery-textarea-inverse"
          />
        </div>
      </div>
      <Row label="Input and Select">
        <div className="grid w-full gap-3 md:grid-cols-3">
          <Input placeholder="Persona name" aria-label="Persona name" data-testid="gallery-input" />
          <Input
            invalid
            defaultValue="Too long"
            aria-label="Persona name, invalid"
            data-testid="gallery-input-invalid"
          />
          <Select aria-label="Microphone" data-testid="gallery-select" defaultValue="default">
            <option value="default">Default microphone</option>
            <option value="other">Other microphone</option>
          </Select>
        </div>
      </Row>
      <Row label="Textarea · resizable, capped">
        <Textarea
          value={draft}
          onChange={setDraft}
          resize="vertical"
          maxLength={500}
          aria-label="Answer, resizable"
          data-testid="gallery-textarea-resizable"
        />
      </Row>
      <Row label="VerdictChip · lg">
        {RUBRIC_ROWS.map((row) => (
          <VerdictChip key={row} row={row} size="lg" data-testid={`gallery-verdict-${row}`} />
        ))}
      </Row>
      <Row label="VerdictChip · md">
        {RUBRIC_ROWS.map((row) => (
          <VerdictChip key={row} row={row} />
        ))}
      </Row>
    </Section>
  )
}

function OverlaySpecimen() {
  const [modalOpen, setModalOpen] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <Section title="Overlays">
      <Row label="Modal">
        <Button data-testid="gallery-open-modal" onClick={() => setModalOpen(true)}>
          Open modal
        </Button>
        <Modal
          open={modalOpen}
          label="Gallery modal"
          onClose={() => setModalOpen(false)}
          data-testid="gallery-modal"
        >
          <h2 className="text-heading font-semibold text-text-strong">End this session?</h2>
          <p className="text-body-sm text-text-muted">
            The scrim is a token, not a Tailwind opacity modifier: a var() color takes no `/NN`.
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Keep going
            </Button>
            <Button variant="primary" onClick={() => setModalOpen(false)}>
              End session
            </Button>
          </div>
        </Modal>
      </Row>
      <Row label="Sheet">
        <Button data-testid="gallery-open-sheet" onClick={() => setSheetOpen(true)}>
          Open sheet
        </Button>
        <Sheet
          open={sheetOpen}
          label="Gallery sheet"
          onClose={() => setSheetOpen(false)}
          data-testid="gallery-sheet"
        >
          <header className="sticky top-0 flex items-center justify-between border-b border-subtle bg-white p-4">
            <h2 className="text-heading font-semibold text-text-strong">How you're scored</h2>
            <IconButton name="x" aria-label="Close sheet" onClick={() => setSheetOpen(false)} />
          </header>
          <div className="space-y-3 p-4">
            <p className="text-body-sm text-text-muted">
              The drawer is the densest text surface in the app, so it is the one where text-faint's
              reduced recession shows.
            </p>
          </div>
        </Sheet>
      </Row>
    </Section>
  )
}

// WCAG 2.1 relative luminance, so the gallery reports the real ratio for a
// pair rather than a number copied from the spec that could drift from the
// tokens. Reads the computed color off a probe element.
function luminance(rgb: string): number {
  const [r, g, b] = (rgb.match(/\d+(\.\d+)?/g) ?? ["0", "0", "0"]).slice(0, 3).map(Number)
  const channel = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

function ratio(a: string, b: string): string {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return ((hi + 0.05) / (lo + 0.05)).toFixed(2)
}

function ContrastCell({ token, ground }: { token: string; ground: string }) {
  const [value, setValue] = useState("—")

  return (
    <span
      ref={(node) => {
        if (!node) return
        const probe = node.parentElement?.querySelector<HTMLElement>("[data-probe]")
        const groundProbe = document.querySelector<HTMLElement>(`[data-ground="${ground}"]`)
        if (!probe || !groundProbe) return
        const next = ratio(
          getComputedStyle(probe).color,
          getComputedStyle(groundProbe).backgroundColor,
        )
        if (next !== value) setValue(next)
      }}
      className="font-data text-body-sm text-text-body"
    >
      {token} on {ground}: {value}
    </span>
  )
}

export default function Gallery() {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 px-8 py-10">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-display font-semibold text-text-strong">
          Airtight design system
        </h1>
        <p className="max-w-[68ch] text-body text-text-muted">
          Every token and primitive from the federal-panel handoff, rendered once so a combination
          can be checked before a screen consumes it. Development only.
        </p>
      </header>

      <Section title="Color">
        <div className="flex flex-wrap gap-3">
          {SWATCHES.map(({ token, className }) => (
            <div key={token} className="flex w-32 flex-col gap-1.5">
              <div
                data-testid={`gallery-swatch-${token}`}
                data-ground={token}
                className={`h-14 rounded-block border border-subtle ${className}`}
              />
              {/* Label in text-body, never in the swatch color: amber-600 and
                  taupe-600 both fail AA as text. */}
              <span className="font-data text-micro text-text-body">{token}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-1 rounded-card border border-subtle bg-white p-4">
          {TEXT_TOKENS.map((token) => (
            <div key={token} className="flex flex-wrap items-center gap-3">
              <span data-probe className={`text-body text-${token}`}>
                The panel may interrupt.
              </span>
              <ContrastCell token={token} ground="sand-50" />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Type">
        <div className="flex flex-col gap-3 rounded-card border border-subtle bg-white p-6">
          <p
            data-testid="gallery-type-display"
            className="font-display text-display font-semibold text-text-strong"
          >
            Get grilled before they do.
          </p>
          <p className="font-display text-display-sm font-semibold text-text-strong">
            Display small · 30px
          </p>
          <p
            data-testid="gallery-type-quote"
            className="font-display text-quote font-semibold italic text-text-body"
          >
            How do you know that number holds at scale?
          </p>
          <p className="max-w-[68ch] text-body text-text-body">
            Body · 15px/1.65, capped at 68ch. Five questions, three evaluators, about ten minutes,
            scored against a rubric you can read before you start.
          </p>
          <p
            data-testid="gallery-type-display-xs"
            className="font-display text-display-xs font-semibold text-text-strong"
          >
            Display extra small · 24px
          </p>
          <p
            data-testid="gallery-type-heading"
            className="text-heading font-semibold text-text-strong"
          >
            Heading · 17px/1.3
          </p>
          <p
            data-testid="gallery-type-subheading"
            className="text-subheading font-semibold text-text-strong"
          >
            Subheading · 15px/1.35
          </p>
          <p className="text-body-sm text-text-muted">Body small · 13px/1.5</p>
          <MicroCaps>Micro-caps · 12px / 600 / 0.09em</MicroCaps>
          <p data-testid="gallery-type-data" className="font-data text-body-sm text-text-body">
            Data · 04:12 · −2 · SES-4417
          </p>
        </div>
      </Section>

      <Section title="Radius, shadow, motion">
        <Row label="Radius">
          {RADII.map((radius) => (
            <div
              key={radius}
              data-testid={`gallery-radius-${radius}`}
              className={`flex h-16 w-24 items-center justify-center border border-subtle bg-white font-data text-micro text-text-body rounded-${radius}`}
            >
              {radius}
            </div>
          ))}
        </Row>
        <Row label="Shadow">
          {SHADOWS.map((shadow) => (
            <div
              key={shadow}
              data-testid={`gallery-shadow-${shadow}`}
              className={`flex h-16 w-24 items-center justify-center rounded-card bg-white font-data text-micro text-text-body shadow-${shadow}`}
            >
              {shadow}
            </div>
          ))}
        </Row>
        <Row label="Motion">
          <span className="font-data text-body-sm text-text-body">
            press 80ms · hover 130ms · enter 200ms · panel 320ms · no bounce anywhere
          </span>
        </Row>
      </Section>

      <Section title="Icons">
        <div className="flex flex-wrap gap-4">
          {ICON_NAMES.map((name) => (
            <div
              key={name}
              data-testid={`gallery-icon-${name}`}
              className="flex w-24 flex-col items-center gap-2 rounded-block border border-subtle bg-white p-3 text-text-body"
            >
              <Icon name={name} />
              <span className="text-center text-micro leading-tight text-text-muted">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Buttons">
        {BUTTON_VARIANTS.map((variant) => (
          <div
            key={variant}
            className={
              variant === "inverse"
                ? "flex flex-wrap items-center gap-3 rounded-card bg-navy-800 p-4"
                : "flex flex-wrap items-center gap-3"
            }
          >
            <span
              className={[
                "w-24 font-data text-body-sm",
                variant === "inverse" ? "text-text-inverse-muted" : "text-text-faint",
              ].join(" ")}
            >
              {variant}
            </span>
            {BUTTON_SIZES.map((size) => (
              <Button
                key={size}
                variant={variant}
                size={size}
                iconLeft="play"
                data-testid={`gallery-button-${variant}-${size}`}
              >
                Start rehearsal
              </Button>
            ))}
          </div>
        ))}
        <Row label="IconButton">
          <IconButton name="x" aria-label="Close" data-testid="gallery-iconbutton" />
          <IconButton
            name="x"
            aria-label="Dismiss, small"
            size="sm"
            data-testid="gallery-icon-button-sm"
          />
          <IconButton
            name="x"
            aria-label="Dismiss, medium"
            size="md"
            data-testid="gallery-icon-button-md"
          />
        </Row>
        <Row label="Attribute passthrough">
          {/* `title` and `disabled` are native attributes the original prop type
              could not express; 39 call sites need that. */}
          <Button disabled title="Passthrough" data-testid="gallery-button-titled">
            Disabled with a title
          </Button>
        </Row>
      </Section>

      <Section title="Card">
        <Row label="Card · nesting">
          {/* The nested block is rendered inside the card so the rule is
              visible rather than described: sand-50 reads as a step down on
              white and vanishes on the sand page ground. */}
          <Card data-testid="gallery-card" className="w-full space-y-3">
            <MicroCaps as="h3">Concern</MicroCaps>
            <Card nested padding="sm" data-testid="gallery-card-nested">
              <p className="text-body-sm text-text-muted">
                A nested block: one radius step down, sand ground, no shadow.
              </p>
            </Card>
          </Card>
        </Row>
      </Section>

      <Section title="Badges and tags">
        <Row label="Badge">
          <Badge tone="live" data-testid="gallery-badge-live">
            Live
          </Badge>
          <Badge tone="neutral" data-testid="gallery-badge-neutral">
            Not scored
          </Badge>
          <Badge tone="positive" data-testid="gallery-badge-positive">
            Evidence backed
          </Badge>
          <Badge tone="caution" data-testid="gallery-badge-caution">
            Clarification
          </Badge>
          <Badge tone="negative" data-testid="gallery-badge-negative">
            Red line crossed
          </Badge>
        </Row>
        <Row label="Tag">
          <Tag data-testid="gallery-tag-default">Transition risk</Tag>
          <Tag muted data-testid="gallery-tag-muted">
            Cost realism
          </Tag>
          <Tag selected onClick={() => {}} data-testid="gallery-tag-selected">
            All sessions
          </Tag>
          <Tag icon="corner-down-right" data-testid="gallery-tag-icon">
            Follow-up
          </Tag>
        </Row>
      </Section>

      <TextareaSpecimen />

      <OverlaySpecimen />

      <Section title="Micro-caps label">
        <Row label="MicroCaps">
          <MicroCaps data-testid="gallery-microcaps">Briefing topic</MicroCaps>
          <MicroCaps tone="muted" data-testid="gallery-microcaps-muted">
            Muted
          </MicroCaps>
          <MicroCaps tone="faint" data-testid="gallery-microcaps-faint">
            Faint
          </MicroCaps>
        </Row>
        <Row label="MicroCaps · inverse">
          <span className="rounded-card bg-navy-800 px-3 py-2">
            <MicroCaps tone="inverse" as="span" data-testid="gallery-microcaps-inverse">
              Inverse
            </MicroCaps>
          </span>
        </Row>
      </Section>
    </div>
  )
}
