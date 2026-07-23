// The optimistic placeholder shown while a submitted answer is being scored. It
// reuses ChatTurn's layout — question header, right-aligned presenter bubble with
// the just-typed answer — but its reply bubble holds a live StageStepper instead
// of a score, so the presenter sees their answer land immediately and watches the
// pipeline walk its stages rather than staring at a frozen button.

import type { Prompt, Stage } from "../types"
import { PRESENTER_BUBBLE, REPLY_BUBBLE, prettify } from "../lib"
import { StageStepper } from "./StageStepper"

function Spinner() {
  return (
    <span
      className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700"
      aria-hidden
    />
  )
}

export function PendingTurn({
  prompt,
  answer,
  stage,
  elapsed,
  kind = "answer",
}: {
  prompt: Prompt
  answer: string
  stage: Stage
  elapsed: number
  kind?: "answer" | "clarify"
}) {
  return (
    <div className="space-y-3">
      {/* question */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold text-slate-800">{prettify(prompt.persona_id)}</span>
          <span className="text-slate-400">·</span>
          <span className="text-slate-500">{prettify(prompt.concern_id)}</span>
          {prompt.is_follow_up && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700">
              Follow-up
            </span>
          )}
        </div>
        <p className="text-sm text-slate-800">{prompt.prompt}</p>
      </div>

      {/* presenter */}
      <div className="flex justify-end">
        <div className={PRESENTER_BUBBLE}>{answer}</div>
      </div>

      {/* pending reply: a scored answer walks the live stage stepper; a
          clarification is a single quick call, so it just spins with the same
          elapsed clock and a "Not scored" cue matching the finished bubble. */}
      <div className="flex justify-start">
        <div className={REPLY_BUBBLE}>
          {kind === "clarify" ? (
            <div className="flex items-center gap-2 text-xs">
              <Spinner />
              <span className="font-semibold text-slate-700">Asking…</span>
              <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                Not scored
              </span>
              <span className="ml-1 tabular-nums text-slate-400">{elapsed}s</span>
            </div>
          ) : (
            <StageStepper stage={stage} elapsed={elapsed} />
          )}
        </div>
      </div>
    </div>
  )
}
