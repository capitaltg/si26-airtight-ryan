// Per-persona support meter. A shadcn `Progress`-style bar built with Tailwind:
// the fill width tracks support (0–100), and a crossed red-line cap turns it red
// and shows a "pinned" badge so the presenter sees the ceiling is stuck.

import type { Meter } from "../types"
import { meterTone, prettify } from "../lib"
import { PersonaAvatar } from "./PersonaAvatar"
import { Badge } from "./ui/Badge"
import { Card } from "./ui/Card"
import { MicroCaps } from "./ui/MicroCaps"

export function MeterBar({ meter }: { meter: Meter }) {
  const width = Math.max(0, Math.min(100, meter.support))
  // The score always ends the row it sits in, pushed right by `ml-auto` and held
  // in a fixed column so the digits line up between meters.
  const score = (
    <span className="ml-auto min-w-[3ch] text-right font-data tabular-nums text-text-muted">
      {meter.support}
    </span>
  )
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 text-body-sm">
        <span className="flex min-w-0 items-center gap-2 font-medium text-text-body">
          <PersonaAvatar personaId={meter.persona_id} size={20} />
          <span className="truncate">{prettify(meter.persona_id)}</span>
        </span>
        {/* Uncapped, the score rides the name row; capped, it drops to the badge
            row below so the badge gets the full width it needs. */}
        {!meter.capped && score}
      </div>
      {meter.capped && (
        <div className="flex items-center gap-2 text-body-sm">
          <Badge tone="negative" className="whitespace-nowrap">
            Red line crossed
          </Badge>
          {score}
        </div>
      )}
      {/* Purely visual — the persona name and numeric support are already text
          above, so screen readers get the value without an ARIA widget role. */}
      <div className="h-2 w-full overflow-hidden rounded-pill bg-sand-300" aria-hidden="true">
        <div
          className={`h-full rounded-pill transition-all duration-500 ${meterTone(meter.support, meter.capped)}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  )
}

export function MeterPanel({ meters }: { meters: Meter[] }) {
  return (
    <Card className="space-y-3">
      <MicroCaps as="h2">Evaluator support</MicroCaps>
      {meters.map((m) => (
        <MeterBar key={m.persona_id} meter={m} />
      ))}
    </Card>
  )
}
