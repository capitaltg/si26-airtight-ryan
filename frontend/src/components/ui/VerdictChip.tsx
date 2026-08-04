export type Verdict = "evidenceBacked" | "approachCited" | "unsubstantiated" | "dodge" | "redLine"

export const VERDICTS: Verdict[] = [
  "evidenceBacked",
  "approachCited",
  "unsubstantiated",
  "dodge",
  "redLine",
]

// Labels are the handoff's own strings. `unsubstantiated` maps to the amber
// "partial" semantic, but amber-600 fails AA as text (3.77:1 on white), so it
// appears as a tinted fill and border behind text-body — never as the text
// color itself. See tokens.css.
const STYLES: Record<Verdict, { label: string; className: string }> = {
  evidenceBacked: {
    label: "Evidence-backed",
    className: "border-moss-600 bg-white text-moss-600",
  },
  approachCited: {
    label: "Approach cited",
    className: "border-teal-600 bg-white text-teal-600",
  },
  unsubstantiated: {
    label: "Unsubstantiated",
    className: "border-amber-600 bg-amber-600/10 text-text-body",
  },
  dodge: {
    label: "Dodge",
    className: "border-crimson-700 bg-white text-crimson-700",
  },
  redLine: {
    label: "Red line",
    className: "border-crimson-700 bg-crimson-700 text-text-inverse",
  },
}

type VerdictChipProps = {
  verdict: Verdict
  size?: "md" | "lg"
  className?: string
  "data-testid"?: string
}

// 26px at lg, per the prototype's `hint-size`.
export function VerdictChip({ verdict, size = "md", className, ...rest }: VerdictChipProps) {
  const { label, className: tone } = STYLES[verdict]
  return (
    <span
      {...rest}
      className={[
        "inline-flex items-center rounded-chip border font-ui font-semibold uppercase",
        size === "lg"
          ? "h-[26px] px-2.5 text-micro"
          : "h-[22px] px-2 text-[11px] tracking-[0.09em]",
        tone,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label}
    </span>
  )
}
