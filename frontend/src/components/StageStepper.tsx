// The live scoring progress inside a pending turn's reply bubble: three labeled
// steps (Extracting → Scoring → Reacting) with the current one spinning, earlier
// ones checked/dimmed, plus a rising elapsed-seconds clock. Honest stage
// visibility — it mirrors the SSE stages the backend actually walks.

import type { Stage } from "../types"

const STEPS: { stage: Stage; label: string }[] = [
  { stage: "extracting", label: "Extracting" },
  { stage: "scoring", label: "Scoring" },
  { stage: "reacting", label: "Reacting" },
]

function Spinner() {
  return (
    <span
      className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700"
      aria-hidden
    />
  )
}

export function StageStepper({ stage, elapsed }: { stage: Stage; elapsed: number }) {
  const current = STEPS.findIndex((s) => s.stage === stage)

  return (
    <div className="flex items-center gap-2 text-xs">
      {STEPS.map((step, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={step.stage} className="flex items-center gap-2">
            <span
              className={`flex items-center gap-1.5 ${
                active ? "font-semibold text-slate-700" : done ? "text-slate-400" : "text-slate-300"
              }`}
            >
              {active ? <Spinner /> : done ? <span aria-hidden>✓</span> : null}
              {step.label}
            </span>
            {i < STEPS.length - 1 && <span className="text-slate-300">→</span>}
          </div>
        )
      })}
      <span className="ml-1 tabular-nums text-slate-400">{elapsed}s</span>
    </div>
  )
}
