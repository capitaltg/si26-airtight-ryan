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
      className="inline-block h-3 w-3 animate-spin rounded-pill border-2 border-sand-300 border-t-navy-800"
      aria-hidden
    />
  )
}

export function StageStepper({ stage, elapsed }: { stage: Stage; elapsed: number }) {
  const current = STEPS.findIndex((s) => s.stage === stage)

  return (
    <div className="flex items-center gap-2 text-body-sm">
      {STEPS.map((step, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={step.stage} className="flex items-center gap-2">
            <span
              className={`flex items-center gap-1.5 ${
                active
                  ? "font-semibold text-text-strong"
                  : done
                    ? "text-text-muted"
                    : "text-text-faint"
              }`}
            >
              {active ? <Spinner /> : done ? <span aria-hidden>✓</span> : null}
              {step.label}
            </span>
            {i < STEPS.length - 1 && <span className="text-text-faint">→</span>}
          </div>
        )
      })}
      <span className="ml-1 font-data tabular-nums text-text-faint">{elapsed}s</span>
    </div>
  )
}
