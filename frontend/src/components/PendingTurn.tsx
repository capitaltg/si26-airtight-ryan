// The optimistic placeholder shown while a submitted answer is being scored. It
// reuses ChatTurn's layout — question header, right-aligned presenter bubble with
// the just-typed answer — but its reply bubble holds a live StageStepper instead
// of a score, so the presenter sees their answer land immediately and watches the
// pipeline walk its stages rather than staring at a frozen button.

import type { Prompt, Stage } from "../types"
import { PRESENTER_BUBBLE, REPLY_BUBBLE, prettify } from "../lib"
import { StageStepper } from "./StageStepper"

export function PendingTurn({
  prompt,
  answer,
  stage,
  elapsed,
}: {
  prompt: Prompt
  answer: string
  stage: Stage
  elapsed: number
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

      {/* pending reply: live stage stepper in place of the score */}
      <div className="flex justify-start">
        <div className={REPLY_BUBBLE}>
          <StageStepper stage={stage} elapsed={elapsed} />
        </div>
      </div>
    </div>
  )
}
