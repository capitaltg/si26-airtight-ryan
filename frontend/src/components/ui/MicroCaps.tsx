import type { ReactNode } from "react"

const TONES = {
  muted: "text-text-muted",
  faint: "text-text-faint",
  inverse: "text-text-inverse-muted",
} as const

type MicroCapsProps = {
  // `label`/`htmlFor` are in the API because MicCheck's device label is a
  // <label> with exactly this typography; `legend` and `dt` because
  // PersonaForm's fieldsets and locked-field list are too.
  as?: "div" | "span" | "p" | "h2" | "h3" | "label" | "legend" | "dt"
  tone?: keyof typeof TONES
  className?: string
  children: ReactNode
  htmlFor?: string
} & { "data-testid"?: string }

// 12px / 600 / 0.09em / uppercase appears 34 times across the handoff — every
// section eyebrow and rail heading. `letter-spacing: 0.09em` is the marker for
// finding them in `docs/design/Airtight.dc.html`.
export function MicroCaps({
  as: Tag = "div",
  tone = "muted",
  className,
  children,
  ...rest
}: MicroCapsProps) {
  return (
    <Tag
      {...rest}
      className={["font-ui text-micro font-semibold uppercase", TONES[tone], className]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </Tag>
  )
}
