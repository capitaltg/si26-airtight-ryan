// The after-action report. Everything above the "Not scored" divider is
// code-rendered from the backend's deterministic report: rate stats lead, then
// per-persona meters, then coverage / dodge / contradiction breakdowns, then the
// scored findings — each with the verbatim quote that fired its rubric row. The
// model narrative is last, clearly labeled "Not scored", and never carries a
// number. `print:` utilities let the presenter export it from the browser.

import { useReport } from "../api/client"
import { prettify, rowLabel } from "../lib"
import type { PersonaLine, Report, ScoredFinding } from "../types"
import { MeterPanel } from "./MeterBar"
import { PersonaAvatar } from "./PersonaAvatar"
import { Badge } from "./ui/Badge"
import { Button } from "./ui/Button"
import { Card } from "./ui/Card"
import { MicroCaps } from "./ui/MicroCaps"
import { type RubricRow, VerdictChip } from "./ui/VerdictChip"

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="print:shadow-none">
      <div className="font-data text-display-xs font-semibold tabular-nums text-text-strong">
        {value}
      </div>
      <MicroCaps>{label}</MicroCaps>
      {hint && <div className="mt-0.5 text-body-sm text-text-faint">{hint}</div>}
    </Card>
  )
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between border-b border-subtle py-1.5 text-body-sm last:border-0">
      <span className="text-text-muted">{label}</span>
      <span className="font-data font-semibold tabular-nums text-text-strong">{value}</span>
    </div>
  )
}

function FindingCard({ f }: { f: ScoredFinding }) {
  const total = f.support_value * f.count
  const sign = total > 0 ? `+${total}` : `${total}`
  // dodge and approach_cited carry a category enum (e.g. "non_commitment") as
  // their detail; the rest carry prose, which must stay verbatim.
  const prettifyDetail = f.rubric_row === "dodge" || f.rubric_row === "approach_cited"
  return (
    <Card as="details" padding="sm" className="print:shadow-none">
      <summary className="flex cursor-pointer items-center gap-2 text-body-sm">
        {/* The server owns the rubric vocabulary, so the row id is cast at the
            boundary rather than widening VerdictChip's prop. */}
        <VerdictChip
          row={f.rubric_row as RubricRow}
          label={`${rowLabel(f.rubric_row, f.count)} ${sign}`}
        />
        <span className="flex items-center gap-1.5 text-text-muted">
          <PersonaAvatar personaId={f.persona_id} size={16} />
          {prettify(f.persona_id)} · {prettify(f.concern_id)}
        </span>
        <span className="ml-auto text-micro text-text-faint">turn {f.turn_index + 1}</span>
      </summary>
      <div className="mt-2 space-y-1.5 text-body-sm text-text-muted">
        {f.evidence.map((e, i) => (
          <div key={`${e.span}-${i}`} className="space-y-1">
            {/* No color utility: preflight already defaults every border to
                sand-300, so adding a bare `border` would draw all four sides. */}
            <blockquote className="border-l-2 pl-2 italic text-text-body">“{e.span}”</blockquote>
            {e.detail && (
              <p className="text-text-muted">{prettifyDetail ? prettify(e.detail) : e.detail}</p>
            )}
          </div>
        ))}
      </div>
    </Card>
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
        <div className="rounded-card border border-crimson-700 bg-crimson-100 p-4 text-body-sm text-crimson-700 print:border-crimson-700">
          <span className="font-semibold">Red line crossed.</span>{" "}
          {capped.map((p) => prettify(p.persona_id)).join(", ")} pinned at the cap for the rest of
          the session.
        </div>
      )}

      {/* rate stats lead — length-independent so a short strong run isn't punished */}
      <section className="space-y-3">
        <MicroCaps as="h2">Headline rates</MicroCaps>
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

      {report.limit_findings.length > 0 && (
        <section className="space-y-2">
          <MicroCaps as="h2">Answer limits</MicroCaps>
          <div className="space-y-2">
            {report.limit_findings.map((finding) => {
              const isText = finding.kind === "text_words"
              const measured = isText ? finding.measured.toFixed(0) : finding.measured.toFixed(1)
              const unit = isText ? "words" : "seconds"
              return (
                // Cautionary, not negative: dark text on the amber tint, because
                // amber can never be a text color (spec §3.2).
                <div
                  key={`${finding.turn_index}-${finding.kind}`}
                  className="rounded-card border border-amber-600 bg-amber-100 px-3 py-2 text-body-sm text-text-body print:border-amber-600"
                >
                  <span className="flex items-center gap-1.5">
                    <PersonaAvatar personaId={finding.persona_id} size={16} />
                    Turn {finding.turn_index + 1} · {prettify(finding.persona_id)} ·{" "}
                    {prettify(finding.concern_id)}
                  </span>
                  <div className="text-body-sm">
                    {isText ? "Text length" : "Voice duration"}: {measured} {unit} (
                    {finding.limit_threshold} {unit} limit) · {finding.penalty}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      <div className="grid gap-6 md:grid-cols-[1fr_18rem]">
        <div className="space-y-6">
          {/* breakdown counts */}
          <section className="grid gap-4 sm:grid-cols-2">
            <Card className="print:shadow-none">
              <MicroCaps as="h3" className="mb-1">
                Sub-question coverage
              </MicroCaps>
              <CountRow label="Full" value={cov.full} />
              <CountRow label="Partial" value={cov.partial} />
              <CountRow label="None" value={cov.none} />
            </Card>
            <Card className="print:shadow-none">
              <MicroCaps as="h3" className="mb-1">
                Dodges by type
              </MicroCaps>
              {dodgeTypes.length === 0 ? (
                <p className="py-1.5 text-body-sm text-text-faint">No dodges. Clean run.</p>
              ) : (
                dodgeTypes.map(([type, n]) => (
                  <CountRow key={type} label={prettify(type)} value={n} />
                ))
              )}
            </Card>
          </section>

          {/* scored findings, each with its verbatim quote */}
          <section className="space-y-2">
            <MicroCaps as="h2">Scored findings: every line carries its quote</MicroCaps>
            {report.findings.length === 0 ? (
              <p className="text-body-sm text-text-faint">
                No span-bearing findings were recorded.
              </p>
            ) : (
              <div className="space-y-2">
                {report.findings.map((f) => (
                  // New reports guarantee one finding per turn and row. Legacy
                  // snapshots can still contain several independently upgraded
                  // findings for that pair, so include every evidence value in
                  // the key rather than collapsing a card during reconciliation.
                  <FindingCard
                    key={`${f.turn_index}-${f.rubric_row}-${f.evidence.map((e) => `${e.span}\u0000${e.detail}`).join("\u0001")}`}
                    f={f}
                  />
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

      {/* clarifications — non-scored exchanges, shown so overuse is auditable */}
      {report.clarifications.length > 0 && (
        <section className="space-y-2">
          <MicroCaps as="h2">Clarifications (not scored)</MicroCaps>
          <div className="space-y-2">
            {report.clarifications.map((c, i) => (
              <Card
                key={`${c.concern_id}-${i}`}
                padding="sm"
                className="text-body-sm print:shadow-none"
              >
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">Not scored</Badge>
                  <PersonaAvatar personaId={c.persona_id} size={16} />
                  <span className="text-body-sm text-text-muted">
                    {prettify(c.persona_id)} · {prettify(c.concern_id)}
                  </span>
                </div>
                <p className="mt-1.5 text-text-body">
                  <MicroCaps as="span">Q: </MicroCaps>
                  {c.question}
                </p>
                <p className="text-text-body">
                  <MicroCaps as="span">A: </MicroCaps>
                  {c.reply}
                </p>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* the one model narrative — explicitly not scored */}
      <section className="space-y-2 border-t-2 border-dashed pt-6">
        <div className="flex items-center gap-2">
          <Badge tone="neutral">{report.narrative.header}</Badge>
          <span className="text-body-sm text-text-faint">model recap: never feeds a score</span>
        </div>
        <p className="text-body leading-relaxed text-text-body">{report.narrative.text}</p>
      </section>
    </div>
  )
}

export function AfterActionReport({ sessionId }: { sessionId: string }) {
  const { data, isLoading, isError, error } = useReport(sessionId, true)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between print:hidden">
        <h1 className="text-display-xs font-semibold text-text-strong">After-action report</h1>
        {data && (
          <Button variant="secondary" size="sm" iconLeft="download" onClick={() => window.print()}>
            Print / export
          </Button>
        )}
      </div>

      {isLoading && <p className="text-body-sm text-text-muted">Building the report…</p>}
      {isError && <p className="text-body-sm text-crimson-700">{(error as Error).message}</p>}
      {data && <ReportBody report={data} />}
    </div>
  )
}
