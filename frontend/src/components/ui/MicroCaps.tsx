import type { ReactNode } from "react"

type MicroCapsProps = {
  as?: "div" | "span" | "p" | "h2" | "h3"
  className?: string
  children: ReactNode
} & { "data-testid"?: string }

// 12px / 600 / 0.09em / uppercase appears 34 times across the handoff — every
// section eyebrow and rail heading. `letter-spacing: 0.09em` is the marker for
// finding them in `docs/design/Airtight.dc.html`.
export function MicroCaps({ as: Tag = "div", className, children, ...rest }: MicroCapsProps) {
  return (
    <Tag
      {...rest}
      className={["font-ui text-micro font-semibold uppercase text-text-muted", className]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </Tag>
  )
}
