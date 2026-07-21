// One exchange in the transcript: the presenter's answer, then the persona's
// in-character reply, plus the code-owned score (delta + matched rubric rows).
// The reply describes the number; it never sets it — so the delta is rendered
// separately from the reply, sourced from the scoring engine.

import type { TranscriptTurn } from "../types"
import { prettify } from "../lib"

function DeltaBadge({ delta, capped }: { delta: number; capped: boolean }) {
  const sign = delta > 0 ? `+${delta}` : `${delta}`
  const tone = capped
    ? "bg-red-100 text-red-700"
    : delta > 0
      ? "bg-emerald-100 text-emerald-700"
      : delta < 0
        ? "bg-orange-100 text-orange-700"
        : "bg-slate-100 text-slate-600"
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold tabular-nums ${tone}`}>
      {sign}
    </span>
  )
}

export function ChatTurn({ turn }: { turn: TranscriptTurn }) {
  return (
    <div className="space-y-3">
      {/* presenter */}
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-slate-800 px-4 py-2.5 text-sm text-white">
          {turn.answer}
        </div>
      </div>

      {/* persona reply + score */}
      <div className="flex justify-start">
        <div className="max-w-[85%] space-y-2 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-2.5 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500">{prettify(turn.personaId)}</span>
            <DeltaBadge delta={turn.supportDelta} capped={turn.capped} />
            {turn.matchedRows.map((r) => (
              <span
                key={r}
                className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
              >
                {r}
              </span>
            ))}
          </div>
          <p className="text-sm text-slate-800">{turn.reply}</p>
          {turn.rationale && (
            <p className="border-t border-slate-100 pt-2 text-xs italic text-slate-500">
              {turn.rationale}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
