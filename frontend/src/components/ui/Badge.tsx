import type { ReactNode } from "react"

type BadgeProps = {
  tone?: "live" | "neutral"
  className?: string
  children: ReactNode
  "data-testid"?: string
}

// 20px, per the prototype's `hint-size`. `tone="live"` carries the only looping
// animation in the system besides the mic pulse that reuses the same keyframe.
export function Badge({ tone = "neutral", className, children, ...rest }: BadgeProps) {
  return (
    <span
      {...rest}
      className={[
        "inline-flex h-5 items-center gap-1.5 rounded-chip px-2",
        "font-ui text-micro font-semibold uppercase",
        tone === "live" ? "bg-crimson-100 text-crimson-700" : "bg-sand-200 text-text-muted",
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
