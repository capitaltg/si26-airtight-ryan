// One exchange in the transcript: the presenter's answer, then the persona's
// in-character reply, plus the code-owned score (delta + matched rubric rows).
// The reply describes the number; it never sets it — so the delta is rendered
// separately from the reply, sourced from the scoring engine.

import type { TranscriptTurn } from "../types"
import { PRESENTER_BUBBLE, REPLY_BUBBLE, prettify, rowLabel } from "../lib"
import { PersonaAvatar } from "./PersonaAvatar"
import { PromptIntro } from "./PromptIntro"
import { Badge, type BadgeTone } from "./ui/Badge"
import { MicroCaps } from "./ui/MicroCaps"
import { type RubricRow, VerdictChip } from "./ui/VerdictChip"

function DeltaBadge({
  delta,
  rawDelta,
  capped,
}: {
  delta: number
  rawDelta: number
  capped: boolean
}) {
  const sign = delta > 0 ? `+${delta}` : `${delta}`
  // Same branch conditions as before; only the rendering moves to Badge tones.
  const tone: BadgeTone = capped
    ? "negative"
    : delta > 0
      ? "positive"
      : delta < 0
        ? "negative"
        : "neutral"
  const rawSign = rawDelta > 0 ? `+${rawDelta}` : `${rawDelta}`
  const clamped = Math.abs(rawDelta) > 2
  const atBound = Math.abs(rawDelta) === 2
  const word = rawDelta < 0 ? "penalty" : "credit"
  const marker = clamped ? `Max · from ${rawSign}` : atBound ? "Max" : null
  const label = clamped
    ? `${sign}, maximum ${word}, reduced from ${rawSign}`
    : atBound
      ? `${sign}, maximum ${word}`
      : undefined
  return (
    <Badge tone={tone} aria-label={label} className="font-data tabular-nums">
      {sign}
      {marker && <span className="ml-1 font-medium normal-case">{marker}</span>}
    </Badge>
  )
}

export function ChatTurn({ turn }: { turn: TranscriptTurn }) {
  const notScored = turn.scored === false
  const edited = turn.transcript != null && turn.transcript !== turn.answer
  const voice = turn.audioUrl != null || edited
  return (
    <div className="space-y-3">
      {/* question */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-body-sm">
          <PersonaAvatar personaId={turn.personaId} size={28} />
          <span className="font-semibold text-text-strong">
            {turn.displayName}, {prettify(turn.personaId)}
          </span>
          <span className="text-text-faint">·</span>
          <span className="text-text-muted">{prettify(turn.concernId)}</span>
          {turn.isFollowUp && <Badge tone="caution">Follow-up</Badge>}
        </div>
        <PromptIntro intro={turn.intro} />
        <p className="text-body text-text-body">{turn.prompt}</p>
      </div>

      {/* presenter */}
      <div className="flex justify-end">
        <div className={PRESENTER_BUBBLE}>
          {voice ? (
            <div className="space-y-1.5">
              <MicroCaps as="span" tone="inverse" className="block">
                What the scorer heard
              </MicroCaps>
              <p>{turn.answer}</p>
              {edited && (
                <details data-testid="original-transcription">
                  <summary>Original transcription</summary>
                  <p>{turn.transcript}</p>
                </details>
              )}
              {turn.audioUrl != null && (
                <>
                  {/* The answer above serves as this clip's caption. A synced
                      <track> would only duplicate it without timing data. */}
                  {/* oxlint-disable-next-line jsx-a11y/media-has-caption */}
                  <audio controls src={turn.audioUrl} className="h-8 w-full" />
                </>
              )}
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
            <PersonaAvatar personaId={turn.personaId} size={28} />
            <span className="text-body-sm font-semibold text-text-muted">
              {turn.displayName}, {prettify(turn.personaId)}
            </span>
            {notScored ? (
              // Clarification: no number moved. Match the report's "Not scored"
              // badge so the visual language is consistent.
              <Badge tone="neutral">Not scored</Badge>
            ) : (
              <>
                <DeltaBadge
                  delta={turn.supportDelta}
                  rawDelta={turn.rawSupportDelta ?? turn.supportDelta}
                  capped={turn.capped}
                />
                {/* The values come straight off the score payload, which is why
                    VerdictChip is keyed on the server's snake_case rubric ids. */}
                {turn.matchedRows.map((r) => (
                  <VerdictChip
                    key={r}
                    row={r as RubricRow}
                    label={rowLabel(r, turn.rowCounts?.[r] ?? 1)}
                  />
                ))}
              </>
            )}
          </div>
          {turn.limit && (
            <p className="text-body-sm text-text-muted">
              {turn.limit.kind === "text_words"
                ? `${turn.limit.measured} words`
                : `${turn.limit.measured.toFixed(1)} seconds`}
              {` / ${turn.limit.limit_threshold} ${turn.limit.kind === "text_words" ? "words" : "seconds"}`}
              {turn.limit.penalty_applied && ` · ${turn.limit.penalty_value} over-limit penalty`}
            </p>
          )}
          <p className="text-body text-text-body">{turn.reply}</p>
          {turn.rationale && (
            <p className="border-t border-subtle pt-2 text-body-sm italic text-text-muted">
              {turn.rationale}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
