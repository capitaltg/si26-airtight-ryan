import type { ReactNode } from "react"

export type BadgeTone = "neutral" | "live" | "positive" | "caution" | "negative"

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-sand-200 text-text-muted",
  live: "bg-crimson-100 text-crimson-700",
  positive: "bg-moss-100 text-moss-600",
  // amber-600 fails AA as text at 3.77:1, so "caution" is dark text on the
  // tint — 9.31:1. See tokens.css and spec §3.2.
  caution: "bg-amber-100 text-text-body",
  negative: "bg-crimson-100 text-crimson-700",
}

type BadgeProps = {
  tone?: BadgeTone
  className?: string
  children: ReactNode
  "data-testid"?: string
}

// 20px, per the prototype's `hint-size`. `tone="live"` carries the only looping
// animation in the system besides the mic pulse that reuses the same keyframe;
// `negative` shares crimson with it but must not animate.
export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span
      {...rest}
      className={[
        "inline-flex h-5 items-center gap-1.5 rounded-chip px-2",
        "font-ui text-micro font-semibold uppercase",
        TONES[tone],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {tone === "live" ? (
        <span className="h-1.5 w-1.5 rounded-pill bg-status-live animate-livePulse" />
      ) : null}
      {children}
    </span>
  )
}
