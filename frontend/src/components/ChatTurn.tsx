// One exchange in the transcript: the presenter's answer, then the persona's
// in-character reply, plus the code-owned score (delta + matched rubric rows).
// The reply describes the number; it never sets it — so the delta is rendered
// separately from the reply, sourced from the scoring engine.

import type { TranscriptTurn } from "../types"
import { PRESENTER_BUBBLE, REPLY_BUBBLE, prettify } from "../lib"
import { PromptIntro } from "./PromptIntro"

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
  const notScored = turn.scored === false
  return (
    <div className="space-y-3">
      {/* question */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold text-slate-800">
            {turn.displayName}, {prettify(turn.personaId)}
          </span>
          <span className="text-slate-400">·</span>
          <span className="text-slate-500">{prettify(turn.concernId)}</span>
          {turn.isFollowUp && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700">
              Follow-up
            </span>
          )}
        </div>
        <PromptIntro intro={turn.intro} />
        <p className="text-sm text-slate-800">{turn.prompt}</p>
      </div>

      {/* presenter */}
      <div className="flex justify-end">
        <div className={PRESENTER_BUBBLE}>
          {turn.transcript ? (
            // Voice mode: the scorer only ever saw the transcript, not the
            // recording, so label it as such and offer the recording itself as
            // a secondary, playable artifact underneath.
            <div className="space-y-1.5">
              <span className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                What the scorer heard
              </span>
              <p>{turn.transcript}</p>
              {/* The transcript above already serves as this clip's caption (it's
                  the verbatim text the scorer read), so a synced <track> would
                  only duplicate it without real timing data to back it. */}
              {/* oxlint-disable-next-line jsx-a11y/media-has-caption */}
              <audio controls src={turn.audioUrl} className="h-8 w-full" />
            </div>
          ) : (
            turn.answer
          )}
        </div>
      </div>

      {/* persona reply + score */}
      <div className="flex justify-start">
        <div className={REPLY_BUBBLE}>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500">
              {turn.displayName}, {prettify(turn.personaId)}
            </span>
            {notScored ? (
              // Clarification: no number moved. Match the report's "Not scored"
              // slate badge so the visual language is consistent.
              <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                Not scored
              </span>
            ) : (
              <>
                <DeltaBadge delta={turn.supportDelta} capped={turn.capped} />
                {turn.matchedRows.map((r) => (
                  <span
                    key={r}
                    className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
                  >
                    {prettify(r)}
                  </span>
                ))}
              </>
            )}
          </div>
          {turn.limit && (
            <p className="text-xs text-slate-500">
              {turn.limit.kind === "text_words"
                ? `${turn.limit.measured} words`
                : `${turn.limit.measured.toFixed(1)} seconds`}
              {` / ${turn.limit.limit_threshold} ${turn.limit.kind === "text_words" ? "words" : "seconds"}`}
              {turn.limit.penalty_applied && ` · ${turn.limit.penalty_value} over-limit penalty`}
            </p>
          )}
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
