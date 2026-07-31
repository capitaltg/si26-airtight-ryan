// Step 2 of the voice turn: the presenter sees what the transcriber heard and
// fixes it before anything is scored. Rehearsal owns the recorded blob, review
// state, and round trips.

import type { TangentLimits } from "../types"

export function VoiceReview({
  rawTranscript,
  text,
  onChange,
  durationSeconds,
  limits,
  submitting,
  error,
  onSubmit,
}: {
  rawTranscript: string
  text: string
  onChange: (next: string) => void
  durationSeconds: number
  limits: TangentLimits | undefined
  submitting: boolean
  error: string | null
  onSubmit: () => void
}) {
  const heardNothing = rawTranscript.trim() === ""

  return (
    <div
      data-testid="voice-review"
      className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="space-y-1">
        <h2 className="text-sm font-semibold text-slate-800">Fix what we heard</h2>
        <p className="text-xs text-slate-500">
          {heardNothing
            ? "Nothing was heard. Type what you said."
            : "Correct anything the transcriber got wrong. Your recording is already locked in."}
        </p>
      </div>
      <textarea
        data-testid="voice-review-text"
        value={text}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        aria-label="What we heard"
        placeholder="What you said…"
        disabled={submitting}
        className="w-full resize-y rounded-md border border-slate-300 p-3 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
      />
      {limits &&
        (() => {
          const policy = limits.voice
          const over = durationSeconds > policy.limit
          const warning = durationSeconds >= policy.warning

          return (
            <p
              data-testid="voice-review-duration"
              className={`text-xs ${over ? "text-red-700" : warning ? "text-amber-700" : "text-slate-500"}`}
            >
              Recorded {durationSeconds.toFixed(1)} / {policy.limit.toFixed(0)} seconds
              {over
                ? ` · Over the ${policy.limit.toFixed(0)}-second limit. This turn takes a ${limits.penalty} penalty.`
                : warning
                  ? ` · Close to the ${policy.limit.toFixed(0)}-second limit.`
                  : ""}
            </p>
          )
        })()}
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm">{error && <span className="text-red-700">{error}</span>}</span>
        <button
          onClick={onSubmit}
          disabled={submitting || !text.trim()}
          className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting ? "Scoring…" : "Submit"}
        </button>
      </div>
    </div>
  )
}
