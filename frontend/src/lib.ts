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

// Chat-bubble class strings shared by a scored turn (ChatTurn) and the pending
// placeholder (PendingTurn) so the two stay visually identical as styles evolve.
export const PRESENTER_BUBBLE =
  "max-w-[85%] rounded-2xl rounded-br-sm bg-slate-800 px-4 py-2.5 text-sm text-white"
export const REPLY_BUBBLE =
  "max-w-[85%] space-y-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-2.5 shadow-sm"

// A red-line cap is crossed once support is pinned at the ceiling; surface it as
// a color threshold so a pinned meter reads as "in trouble" at a glance.
export function meterTone(support: number, capped: boolean): string {
  if (capped) return "bg-red-600"
  if (support >= 60) return "bg-emerald-600"
  if (support >= 35) return "bg-amber-500"
  return "bg-orange-600"
}
