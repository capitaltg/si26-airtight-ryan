// The past-rehearsals list: up to five finished sessions, newest first. Shown on
// the two screens where nobody is mid-answer (the landing screen and the
// after-action report), so it never competes with the rubric drawer or an
// in-flight turn. Each card is a button that opens that session read-only.

import { useHistory } from "../api/client"
import type { HistorySummary } from "../types"
import { MeterBar } from "./MeterBar"

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

// "complete" means the agenda was exhausted; "ended" means the presenter
// stopped early. Both are history, and the difference matters when reading a
// short transcript.
function StatusBadge({ status }: { status: string }) {
  const complete = status === "complete"
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
        complete ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"
      }`}
    >
      {complete ? "Complete" : "Ended early"}
    </span>
  )
}

function HistoryCard({
  session,
  onSelect,
}: {
  session: HistorySummary
  onSelect: (id: string) => void
}) {
  return (
    <button
      type="button"
      data-testid="history-card"
      onClick={() => onSelect(session.id)}
      className="w-full space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
    >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-slate-800">{formatWhen(session.archived_at)}</span>
        <StatusBadge status={session.status} />
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">
          {session.concerns_satisfied} of {session.concerns_total} concerns satisfied
        </span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">
          {session.turn_count} {session.turn_count === 1 ? "turn" : "turns"}
        </span>
      </div>
      <div className="space-y-2">
        {session.meters.map((meter) => (
          <MeterBar key={meter.persona_id} meter={meter} />
        ))}
      </div>
    </button>
  )
}

export function HistoryList({ onSelect }: { onSelect: (id: string) => void }) {
  const { data, isLoading, isError, error } = useHistory()

  return (
    <section data-testid="history-list" className="w-full max-w-2xl space-y-3 text-left">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Past rehearsals
      </h2>
      {isLoading && <p className="text-sm text-slate-500">Loading past rehearsals…</p>}
      {isError && <p className="text-sm text-red-700">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-400">
          Finished rehearsals appear here. The five most recent are kept.
        </p>
      )}
      {data?.map((session) => (
        <HistoryCard key={session.id} session={session} onSelect={onSelect} />
      ))}
    </section>
  )
}
