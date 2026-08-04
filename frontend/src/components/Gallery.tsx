import type { ReactNode } from "react"

import { Badge } from "./ui/Badge"
import { Button, type ButtonSize, type ButtonVariant } from "./ui/Button"
import { Icon, ICON_NAMES } from "./ui/Icon"
import { IconButton } from "./ui/IconButton"
import { MicroCaps } from "./ui/MicroCaps"
import { Tag } from "./ui/Tag"

// Development-only surface. The repo has no Storybook and SP1 changes no
// screen, so this is where a token or primitive is checked before a screen
// consumes it in SP3–SP7. Mounted from App.tsx behind `import.meta.env.DEV`.

const BUTTON_VARIANTS: ButtonVariant[] = ["primary", "secondary", "ghost", "inverse", "danger"]
const BUTTON_SIZES: ButtonSize[] = ["sm", "md", "lg"]

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

      <Section title="Icons">
        <div className="flex flex-wrap gap-4">
          {ICON_NAMES.map((name) => (
            <div
              key={name}
              data-testid={`gallery-icon-${name}`}
              className="flex w-24 flex-col items-center gap-2 rounded-block border border-subtle bg-white p-3 text-text-body"
            >
              <Icon name={name} />
              <span className="text-center text-[10px] leading-tight text-text-muted">{name}</span>
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

      <Section title="Micro-caps label">
        <Row label="MicroCaps">
          <MicroCaps data-testid="gallery-microcaps">Briefing topic</MicroCaps>
        </Row>
      </Section>
    </div>
  )
}
