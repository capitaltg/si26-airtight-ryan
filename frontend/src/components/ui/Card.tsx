import type { ReactNode } from "react"

const PADDING = { none: "", sm: "p-3", md: "p-4" } as const

type CardProps = {
  // `details` is in the union for RubricPanel's collapsible concern blocks.
  as?: "div" | "section" | "article" | "li" | "details"
  padding?: keyof typeof PADDING
  /** A block inside another card: one radius step down, sand ground, no shadow. */
  nested?: boolean
  className?: string
  children: ReactNode
  /** Rehearsal's mic-check panel is the target of an `aria-controls`. */
  id?: string
  "data-testid"?: string
}

// The `rounded-card border-subtle bg-white shadow` surface, which appears about
// twenty times across the app. `nested` is the inside-a-card variant: sand-50 on
// white reads as a step down, whereas sand-50 on the sand page ground vanishes —
// which is why the enclosing surface, not the element, picks the fill (spec §3.2).
//
// No `interactive` prop. HistoryList's row *is* a <button> carrying the click
// target, while PersonaEditor's row is a <div> wrapping one; a single prop would
// force one of them to change its accessible markup during a styling pass.
export function Card({
  as: Element = "div",
  padding = "md",
  nested = false,
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <Element
      {...rest}
      className={[
        nested
          ? "rounded-block border border-subtle bg-sand-50"
          : "rounded-card border border-subtle bg-white shadow",
        PADDING[padding],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </Element>
  )
}
