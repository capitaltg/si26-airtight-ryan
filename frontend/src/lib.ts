// Small presentation helpers shared across components.

// The API exposes personas and concerns by snake_case id only. Prettify them for
// display: "technical_evaluator" -> "Technical Evaluator". For a presenter, the
// role label reads better than the authored first name (which the API omits).
export function prettify(id: string): string {
  return id
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

// A red-line cap is crossed once support is pinned at the ceiling; surface it as
// a color threshold so a pinned meter reads as "in trouble" at a glance.
export function meterTone(support: number, capped: boolean): string {
  if (capped) return "bg-red-600"
  if (support >= 60) return "bg-emerald-600"
  if (support >= 35) return "bg-amber-500"
  return "bg-orange-600"
}
