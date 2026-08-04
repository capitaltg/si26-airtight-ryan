// Small presentation helpers shared across components.

// Concerns (and the persona role label alongside a name) are exposed by
// snake_case id only. Prettify them for display: "technical_evaluator" ->
// "Technical Evaluator".
export function prettify(id: string): string {
  return id
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

export function rowLabel(row: string, count = 1): string {
  return count > 1 ? `${prettify(row)} x${count}` : prettify(row)
}

export function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

// Chat-bubble class strings shared by a scored turn (ChatTurn) and the pending
// placeholder (PendingTurn) so the two stay visually identical as styles evolve.
// The bubbles are a deviation from the handoff, which uses bordered blocks:
// reshaping them is structural, so they keep their tails (spec §4 item 2). The
// directional tail corners are exempt from the radius rule.
export const PRESENTER_BUBBLE =
  "max-w-[85%] rounded-card rounded-br-chip bg-navy-800 px-4 py-2.5 text-body-sm text-text-inverse"
export const REPLY_BUBBLE =
  "max-w-[85%] space-y-2 rounded-card rounded-bl-chip border border-subtle bg-white px-4 py-2.5 shadow-sm"

// A red-line cap is crossed once support is pinned at the ceiling; surface it as
// a color threshold so a pinned meter reads as "in trouble" at a glance.
// amber-600 as a *fill* is fine; the ban is on amber as text.
export function meterTone(support: number, capped: boolean): string {
  if (capped) return "bg-crimson-700"
  if (support >= 60) return "bg-moss-600"
  if (support >= 35) return "bg-amber-600"
  return "bg-sand-300"
}
