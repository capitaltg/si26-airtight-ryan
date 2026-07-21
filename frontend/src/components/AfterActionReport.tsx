// The after-action report. Everything above the "Not scored" divider is
// code-rendered from the backend's deterministic report: rate stats lead, then
// per-persona meters, then coverage / dodge / contradiction breakdowns, then the
// scored findings — each with the verbatim quote that fired its rubric row. The
// model narrative is last, clearly labeled "Not scored", and never carries a
// number. `print:` utilities let the presenter export it from the browser.

import { useReport } from "../api/client"
import { prettify } from "../lib"
import type { PersonaLine, Report, ScoredFinding } from "../types"
import { MeterPanel } from "./MeterBar"

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
      <div className="text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      <div className="text-xs font-medium text-slate-500">{label}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-400">{hint}</div>}
    </div>
  )
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-0">
      <span className="text-slate-600">{label}</span>
      <span className="tabular-nums font-semibold text-slate-800">{value}</span>
    </div>
  )
}

const ROW_TONE: Record<string, string> = {
  red_line: "bg-red-100 text-red-700",
  dodge: "bg-orange-100 text-orange-700",
  false_fact: "bg-orange-100 text-orange-700",
  approach_cited: "bg-emerald-100 text-emerald-700",
  evidence_backed: "bg-emerald-100 text-emerald-700",
}

function FindingCard({ f }: { f: ScoredFinding }) {
  const tone = ROW_TONE[f.rubric_row] ?? "bg-slate-100 text-slate-600"
  const sign = f.support_value > 0 ? `+${f.support_value}` : `${f.support_value}`
  return (
    <details className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm print:shadow-none print:open">
      <summary className="flex cursor-pointer items-center gap-2 text-sm">
        <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${tone}`}>
          {prettify(f.rubric_row)} {sign}
        </span>
        <span className="text-slate-500">
          {prettify(f.persona_id)} · {prettify(f.concern_id)}
        </span>
        <span className="ml-auto text-xs text-slate-400">turn {f.turn_index + 1}</span>
      </summary>
      <div className="mt-2 space-y-1.5 text-xs text-slate-600">
        <blockquote className="border-l-2 border-slate-300 pl-2 italic text-slate-700">
          “{f.span}”
        </blockquote>
        {f.detail && <p className="text-slate-500">{f.detail}</p>}
      </div>
    </details>
  )
}

function ReportBody({ report }: { report: Report }) {
  const rs = report.rate_stats
  const cov = report.coverage_counts
  const meters = report.personas.map((p: PersonaLine) => ({
    persona_id: p.persona_id,
    support: p.support,
    capped: p.capped,
  }))
  const capped = report.personas.filter((p) => p.capped)
  const dodgeTypes = Object.entries(report.dodge_counts_by_type)

  return (
    <div className="space-y-6">
      {capped.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 print:border-red-400">
          <span className="font-semibold">Red line crossed.</span>{" "}
          {capped.map((p) => prettify(p.persona_id)).join(", ")} pinned at the cap for the rest of
          the session.
        </div>
      )}

      {/* rate stats lead — length-independent so a short strong run isn't punished */}
      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Headline rates
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile
            label="Concerns satisfied"
            value={`${rs.concerns_satisfied}/${rs.concerns_total}`}
            hint={`${pct(rs.coverage_rate)} coverage rate`}
          />
          <StatTile
            label="Dodges per turn"
            value={rs.dodges_per_turn.toFixed(2)}
            hint={`${rs.dodge_count} of ${rs.total_turns} turns`}
          />
          <StatTile label="Contradictions" value={`${rs.contradiction_count}`} />
          <StatTile label="Turns" value={`${rs.total_turns}`} />
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-[1fr_18rem]">
        <div className="space-y-6">
          {/* breakdown counts */}
          <section className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Sub-question coverage
              </h3>
              <CountRow label="Full" value={cov.full} />
              <CountRow label="Partial" value={cov.partial} />
              <CountRow label="None" value={cov.none} />
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Dodges by type
              </h3>
              {dodgeTypes.length === 0 ? (
                <p className="py-1.5 text-sm text-slate-400">No dodges. Clean run.</p>
              ) : (
                dodgeTypes.map(([type, n]) => (
                  <CountRow key={type} label={prettify(type)} value={n} />
                ))
              )}
            </div>
          </section>

          {/* scored findings, each with its verbatim quote */}
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Scored findings: every line carries its quote
            </h2>
            {report.findings.length === 0 ? (
              <p className="text-sm text-slate-400">No span-bearing findings were recorded.</p>
            ) : (
              <div className="space-y-2">
                {report.findings.map((f) => (
                  <FindingCard key={`${f.turn_index}-${f.rubric_row}-${f.span}`} f={f} />
                ))}
              </div>
            )}
          </section>
        </div>

        {/* final evaluator support */}
        <div className="md:sticky md:top-6 md:self-start">
          <MeterPanel meters={meters} />
        </div>
      </div>

      {/* the one model narrative — explicitly not scored */}
      <section className="space-y-2 border-t-2 border-dashed border-slate-300 pt-6">
        <div className="flex items-center gap-2">
          <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
            {report.narrative.header}
          </span>
          <span className="text-xs text-slate-400">model recap: never feeds a score</span>
        </div>
        <p className="text-sm leading-relaxed text-slate-700">{report.narrative.text}</p>
      </section>
    </div>
  )
}

export function AfterActionReport({ sessionId }: { sessionId: string }) {
  const { data, isLoading, isError, error } = useReport(sessionId, true)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between print:hidden">
        <h1 className="text-xl font-semibold text-slate-900">After-action report</h1>
        {data && (
          <button
            onClick={() => window.print()}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
          >
            Print / export
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-500">Building the report…</p>}
      {isError && <p className="text-sm text-red-700">{(error as Error).message}</p>}
      {data && <ReportBody report={data} />}
    </div>
  )
}
