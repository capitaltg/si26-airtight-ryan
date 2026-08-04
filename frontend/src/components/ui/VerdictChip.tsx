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

// `RubricDisclosure.rows[].id` is a bare `string` on the wire, so a caller that
// renders straight from the rubric endpoint needs this before it can pick a tone.
// A row the server grows and the chip has no tone for falls back to plain text
// rather than an untoned chip.
export function isRubricRow(id: string): id is RubricRow {
  return (RUBRIC_ROWS as string[]).includes(id)
}

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

// Every chip is filled with its own tone's tint, so the fill is a second reading
// of the verdict rather than a shape that happens to be white. It also stops the
// chip from dissolving into its ground: all three call sites render on white
// (`REPLY_BUBBLE`, the report's `Card`, the rubric drawer), where a `bg-white`
// chip had only its border to separate it from the surface behind it.
//
// The two ends of the ladder are solid rather than tinted, and they are the only
// two: `evidence_backed` is the best a turn can do and `red_line` the worst, so
// each reads as a verdict on sight instead of one tint among eight. The rows
// between them stay tinted.
//
// Contrast, measured, all AA at 12px: moss tint 4.89, crimson tint 8.07,
// text-body on amber 9.87, text-inverse on solid moss 5.57, on solid crimson 9.62.
const TONES: Record<RubricRow, string> = {
  evidence_backed: "border-moss-600 bg-moss-600 text-text-inverse",
  // Moss, not teal: the two positive rows now share one family, and the tint is
  // the quieter of the pair against `evidence_backed`'s solid fill.
  approach_cited: "border-moss-600 bg-moss-100 text-moss-600",
  // The three cautionary rows share amber. amber-600 cannot be text (3.77:1), so
  // amber is the one tone whose label is text-body rather than the accent itself.
  unsubstantiated: "border-amber-600 bg-amber-100 text-text-body",
  contradiction: "border-amber-600 bg-amber-100 text-text-body",
  over_limit: "border-amber-600 bg-amber-100 text-text-body",
  dodge: "border-crimson-700 bg-crimson-100 text-crimson-700",
  false_fact: "border-crimson-700 bg-crimson-100 text-crimson-700",
  // Solid, the crimson counterpart to `evidence_backed`: red_line is the top of
  // the escalation, and nothing below it may look like it.
  red_line: "border-crimson-700 bg-crimson-700 text-text-inverse",
}

type VerdictChipProps = {
  row: RubricRow
  size?: "md" | "lg"
  /**
   * Overrides the row's label. ChatTurn passes `rowLabel(row, count)` so a row
   * that fired twice still reads "False Fact x2"; the tone still comes from `row`.
   */
  label?: string
  className?: string
  "data-testid"?: string
}

// 26px at lg, per the prototype's `hint-size`. Both sizes sit on the type ramp's
// `micro` step; the shorter chip gets there by height and padding, not by an
// off-ramp 11px size.
export function VerdictChip({ row, size = "md", label, className, ...rest }: VerdictChipProps) {
  return (
    <span
      {...rest}
      className={[
        "inline-flex items-center whitespace-nowrap rounded-chip border font-ui text-micro font-semibold uppercase",
        size === "lg" ? "h-[26px] px-2.5" : "h-[22px] px-2",
        TONES[row],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {label ?? LABELS[row]}
    </span>
  )
}
