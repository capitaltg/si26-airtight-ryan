// The optimistic placeholder shown while a submitted answer is being scored. It
// reuses ChatTurn's layout — question header, right-aligned presenter bubble with
// the just-typed answer — but its reply bubble holds a live StageStepper instead
// of a score, so the presenter sees their answer land immediately and watches the
// pipeline walk its stages rather than staring at a frozen button.

import type { Prompt, Stage } from "../types"
import { PRESENTER_BUBBLE, REPLY_BUBBLE, prettify } from "../lib"
import { PersonaAvatar } from "./PersonaAvatar"
import { PromptIntro } from "./PromptIntro"
import { StageStepper } from "./StageStepper"
import { Badge } from "./ui/Badge"

function Spinner() {
  return (
    <span
      className="inline-block h-3 w-3 animate-spin rounded-pill border-2 border-sand-300 border-t-navy-800"
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
        <div className="flex items-center gap-2 text-body-sm">
          <PersonaAvatar personaId={prompt.persona_id} size={28} />
          <span className="font-semibold text-text-strong">{prettify(prompt.persona_id)}</span>
          <span className="text-text-faint">·</span>
          <span className="text-text-muted">{prettify(prompt.concern_id)}</span>
          {prompt.is_follow_up && <Badge tone="caution">Follow-up</Badge>}
        </div>
        <PromptIntro intro={prompt.intro} />
        <p className="text-body text-text-body">{prompt.prompt}</p>
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
            <div className="flex items-center gap-2 text-body-sm">
              <Spinner />
              <span className="font-semibold text-text-body">Asking…</span>
              <Badge tone="neutral">Not scored</Badge>
              <span className="ml-1 font-data tabular-nums text-text-faint">{elapsed}s</span>
            </div>
          ) : (
            <StageStepper stage={stage} elapsed={elapsed} />
          )}
        </div>
      </div>
    </div>
  )
}
