// One past rehearsal, read-only: its transcript rebuilt from the server's stored
// rows, then its archived after-action report. Both render through the same
// components the live rehearsal uses, so an archived turn looks exactly like the
// turn the presenter saw at the time.

import { useArchivedTranscript } from "../api/client"
import type { ArchivedTurn, TranscriptTurn } from "../types"
import { AfterActionReport } from "./AfterActionReport"
import { ChatTurn } from "./ChatTurn"
import { Button } from "./ui/Button"
import { MicroCaps } from "./ui/MicroCaps"

// `key` is client-only (React list order) and `audioUrl` has nothing to point at:
// the recording is dropped when the session is archived. The original
// transcription remains available behind ChatTurn's disclosure when it differs
// from the answer the scorer received.
function toTranscriptTurn(turn: ArchivedTurn, index: number): TranscriptTurn {
  return {
    key: index,
    personaId: turn.persona_id,
    displayName: turn.display_name,
    concernId: turn.concern_id,
    isFollowUp: turn.is_follow_up,
    prompt: turn.prompt,
    intro: turn.intro,
    answer: turn.answer,
    transcript: turn.transcript ?? undefined,
    reply: turn.reply,
    rationale: turn.rationale,
    supportDelta: turn.support_delta,
    rawSupportDelta: turn.raw_support_delta ?? turn.support_delta,
    matchedRows: turn.matched_rows,
    rowCounts: turn.row_counts ?? {},
    capped: turn.capped,
    limit: turn.limit,
    scored: turn.scored,
  }
}

export function ArchiveView({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const { data, isLoading, isError, error } = useArchivedTranscript(sessionId)
  const turns = (data?.turns ?? []).map(toTranscriptTurn)

  return (
    <div data-testid="archive-view" className="space-y-4">
      <div className="flex items-center justify-between print:hidden">
        {/* The icon set has no left-pointing glyph, and the ← is the button's
            existing accessible name, so the text carries the direction. */}
        <Button variant="ghost" size="sm" onClick={onBack}>
          ← Back
        </Button>
        <MicroCaps tone="faint">Past rehearsal, read-only</MicroCaps>
      </div>

      {/* On the page ground, so sand-200 rather than sand-50: sand-50 on sand-50
          is invisible (spec §3.2). */}
      <div className="space-y-4 rounded-card border border-subtle bg-sand-200 p-4">
        {isLoading && <p className="text-body-sm text-text-muted">Loading the transcript…</p>}
        {isError && <p className="text-body-sm text-crimson-700">{(error as Error).message}</p>}
        {data && turns.length === 0 && (
          <p className="text-body-sm text-text-faint">
            This rehearsal ended before any question was answered.
          </p>
        )}
        {turns.map((turn) => (
          <ChatTurn key={turn.key} turn={turn} />
        ))}
      </div>

      <AfterActionReport sessionId={sessionId} />
    </div>
  )
}
