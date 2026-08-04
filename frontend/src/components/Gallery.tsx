import type { ReactNode } from "react"

import { Icon, ICON_NAMES } from "./ui/Icon"
import { MicroCaps } from "./ui/MicroCaps"

// Development-only surface. The repo has no Storybook and SP1 changes no
// screen, so this is where a token or primitive is checked before a screen
// consumes it in SP3–SP7. Mounted from App.tsx behind `import.meta.env.DEV`.

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

      <Section title="Micro-caps label">
        <Row label="MicroCaps">
          <MicroCaps data-testid="gallery-microcaps">Briefing topic</MicroCaps>
        </Row>
      </Section>
    </div>
  )
}
