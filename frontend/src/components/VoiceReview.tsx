// Step 2 of the voice turn: the presenter sees what the transcriber heard and
// fixes it before anything is scored. Rehearsal owns the recorded blob, review
// state, and round trips.

import type { TangentLimits } from "../types"
import { Button } from "./ui/Button"
import { Card } from "./ui/Card"
import { Textarea } from "./ui/Textarea"

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
    <Card data-testid="voice-review" className="space-y-2">
      <div className="space-y-1">
        <h2 className="text-heading font-semibold text-text-strong">Fix what we heard</h2>
        <p className="text-body-sm text-text-muted">
          {heardNothing
            ? "Nothing was heard. Type what you said."
            : "Correct anything the transcriber got wrong. Your recording is already locked in."}
        </p>
      </div>
      <Textarea
        data-testid="voice-review-text"
        value={text}
        onChange={onChange}
        rows={4}
        resize="vertical"
        aria-label="What we heard"
        placeholder="What you said…"
        disabled={submitting}
      />
      {limits &&
        (() => {
          const policy = limits.voice
          const over = durationSeconds > policy.limit
          const warning = durationSeconds >= policy.warning

          return (
            // The near-limit cue cannot be amber text (3.77:1 fails AA), so it
            // is dark text on the amber tint instead — the same pair Badge
            // tone="caution" uses, without the uppercase chip shape a whole
            // sentence cannot take.
            <p
              data-testid="voice-review-duration"
              className={`text-body-sm ${
                over
                  ? "text-crimson-700"
                  : warning
                    ? "inline-block rounded-chip bg-amber-100 px-1.5 text-text-body"
                    : "text-text-muted"
              }`}
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
        <span className="text-body-sm">
          {error && <span className="text-crimson-700">{error}</span>}
        </span>
        <Button variant="primary" onClick={onSubmit} disabled={submitting || !text.trim()}>
          {submitting ? "Scoring…" : "Submit"}
        </Button>
      </div>
    </Card>
  )
}
