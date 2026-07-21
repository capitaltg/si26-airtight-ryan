// Per-persona support meter. A shadcn `Progress`-style bar built with Tailwind:
// the fill width tracks support (0–100), and a crossed red-line cap turns it red
// and shows a "pinned" badge so the presenter sees the ceiling is stuck.

import type { Meter } from "../types"
import { meterTone, prettify } from "../lib"

export function MeterBar({ meter }: { meter: Meter }) {
  const width = Math.max(0, Math.min(100, meter.support))
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium text-slate-700">{prettify(meter.persona_id)}</span>
        <span className="flex items-center gap-2 tabular-nums text-slate-500">
          {meter.capped && (
            <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700">
              Red line crossed
            </span>
          )}
          {meter.support}
        </span>
      </div>
      {/* Purely visual — the persona name and numeric support are already text
          above, so screen readers get the value without an ARIA widget role. */}
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200" aria-hidden="true">
        <div
          className={`h-full rounded-full transition-all duration-500 ${meterTone(meter.support, meter.capped)}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  )
}

export function MeterPanel({ meters }: { meters: Meter[] }) {
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Evaluator support
      </h2>
      {meters.map((m) => (
        <MeterBar key={m.persona_id} meter={m} />
      ))}
    </div>
  )
}
