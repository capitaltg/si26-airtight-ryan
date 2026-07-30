// One past rehearsal, read-only: its transcript rebuilt from the server's stored
// rows, then its archived after-action report. Both render through the same
// components the live rehearsal uses, so an archived turn looks exactly like the
// turn the presenter saw at the time.

import { useArchivedTranscript } from "../api/client"
import type { ArchivedTurn, TranscriptTurn } from "../types"
import { AfterActionReport } from "./AfterActionReport"
import { ChatTurn } from "./ChatTurn"

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
    matchedRows: turn.matched_rows,
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
        <button
          onClick={onBack}
          className="text-sm font-medium text-slate-500 hover:text-slate-800"
        >
          ← Back
        </button>
        <span className="text-sm text-slate-400">Past rehearsal, read-only</span>
      </div>

      <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
        {isLoading && <p className="text-sm text-slate-500">Loading the transcript…</p>}
        {isError && <p className="text-sm text-red-700">{(error as Error).message}</p>}
        {data && turns.length === 0 && (
          <p className="text-sm text-slate-400">
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
