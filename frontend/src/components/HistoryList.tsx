// The past-rehearsals list: up to five finished sessions, newest first. Shown on
// the two screens where nobody is mid-answer (the landing screen and the
// after-action report), so it never competes with the rubric drawer or an
// in-flight turn. Each card is a button that opens that session read-only.

import { useHistory } from "../api/client"
import type { HistorySummary } from "../types"
import { MeterBar } from "./MeterBar"
import { Badge } from "./ui/Badge"
import { MicroCaps } from "./ui/MicroCaps"

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
    <Badge tone={complete ? "positive" : "neutral"}>{complete ? "Complete" : "Ended early"}</Badge>
  )
}

function HistoryCard({
  session,
  onSelect,
}: {
  session: HistorySummary
  onSelect: (id: string) => void
}) {
  // The row *is* the click target, so it takes the card classes directly rather
  // than nesting inside a Card: wrapping a button in a padded div would move the
  // click target.
  return (
    <button
      type="button"
      data-testid="history-card"
      onClick={() => onSelect(session.id)}
      className="w-full space-y-3 rounded-card border border-subtle bg-white p-4 text-left shadow transition-colors duration-hover ease-in hover:border-taupe-600 hover:bg-sand-50 focus-visible:shadow-focus focus-visible:outline-none"
    >
      <div className="flex flex-wrap items-center gap-2 text-body-sm">
        <span className="font-semibold text-text-strong">{formatWhen(session.archived_at)}</span>
        <StatusBadge status={session.status} />
        <span className="text-text-faint">·</span>
        <span className="text-text-muted">
          {session.concerns_satisfied} of {session.concerns_total} concerns satisfied
        </span>
        <span className="text-text-faint">·</span>
        <span className="text-text-muted">
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
      <MicroCaps as="h2">Past rehearsals</MicroCaps>
      {isLoading && <p className="text-body-sm text-text-muted">Loading past rehearsals…</p>}
      {isError && <p className="text-body-sm text-crimson-700">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <p className="text-body-sm text-text-muted">
          Finished rehearsals appear here. The five most recent are kept.
        </p>
      )}
      {data?.map((session) => (
        <HistoryCard key={session.id} session={session} onSelect={onSelect} />
      ))}
    </section>
  )
}
