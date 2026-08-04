// The eight rows in server/app/content/store/rubric.yaml, in the server's own
// snake_case so no translation layer exists between the score payload and the
// chip.
export type RubricRow =
  | "evidence_backed"
  | "approach_cited"
  | "unsubstantiated"
  | "contradiction"
  | "over_limit"
  | "dodge"
  | "false_fact"
  | "red_line"

export const RUBRIC_ROWS: RubricRow[] = [
  "evidence_backed",
  "approach_cited",
  "unsubstantiated",
  "contradiction",
  "over_limit",
  "dodge",
  "false_fact",
  "red_line",
]

// Sentence case, not `prettify()`: that helper title-cases every word, so
// `red_line` would read "Red Line". `prettify` is used in 20 other places and is
// not changed here.
const LABELS: Record<RubricRow, string> = {
  evidence_backed: "Evidence-backed",
  approach_cited: "Approach cited",
  unsubstantiated: "Unsubstantiated",
  contradiction: "Contradiction",
  over_limit: "Over limit",
  dodge: "Dodge",
  false_fact: "False fact",
  red_line: "Red line",
}

const TONES: Record<RubricRow, string> = {
  evidence_backed: "border-moss-600 bg-white text-moss-600",
  approach_cited: "border-teal-600 bg-white text-teal-600",
  // The three cautionary rows share amber. amber-600 cannot be text (3.77:1),
  // so the tone is a tint plus a full-weight border behind text-body.
  unsubstantiated: "border-amber-600 bg-amber-100 text-text-body",
  contradiction: "border-amber-600 bg-amber-100 text-text-body",
  over_limit: "border-amber-600 bg-amber-100 text-text-body",
  dodge: "border-crimson-700 bg-white text-crimson-700",
  false_fact: "border-crimson-700 bg-white text-crimson-700",
  red_line: "border-crimson-700 bg-crimson-700 text-text-inverse",
}

type VerdictChipProps = {
  row: RubricRow
  size?: "md" | "lg"
  className?: string
  "data-testid"?: string
}

// 26px at lg, per the prototype's `hint-size`. Both sizes sit on the type ramp's
// `micro` step; the shorter chip gets there by height and padding, not by an
// off-ramp 11px size.
export function VerdictChip({ row, size = "md", className, ...rest }: VerdictChipProps) {
  return (
    <span
      {...rest}
      className={[
        "inline-flex items-center rounded-chip border font-ui text-micro font-semibold uppercase",
        size === "lg" ? "h-[26px] px-2.5" : "h-[22px] px-2",
        TONES[row],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {LABELS[row]}
    </span>
  )
}
