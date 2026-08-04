import type { ReactNode } from "react"

const TONES = {
  muted: "text-text-muted",
  faint: "text-text-faint",
  inverse: "text-text-inverse-muted",
} as const

type MicroCapsProps = {
  // `"label"` and `htmlFor` are in the API because MicCheck's device label and
  // PersonaForm's field labels are <label> elements with exactly this typography.
  as?: "div" | "span" | "p" | "h2" | "h3" | "label"
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
