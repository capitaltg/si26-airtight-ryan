// "How you're scored" drawer — the disclosed rubric (spec: the rubric is shown,
// not hidden). The slide-in itself is the `Sheet` primitive, which owns the
// scrim, the backdrop click, and the Escape listener; this component owns the
// content.

import { useRubric } from "../api/client"
import { prettify } from "../lib"
import { Badge } from "./ui/Badge"
import { Card } from "./ui/Card"
import { IconButton } from "./ui/IconButton"
import { MicroCaps } from "./ui/MicroCaps"
import { Sheet } from "./ui/Sheet"

export function RubricPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data, isLoading, isError } = useRubric()

  return (
    <Sheet open={open} onClose={onClose} label="How you're scored">
      <header className="sticky top-0 flex items-center justify-between border-b border-subtle bg-white px-5 py-4">
        <div>
          <h2 className="text-heading font-semibold text-text-strong">How you&apos;re scored</h2>
          {data && (
            <p className="text-body-sm text-text-muted">
              Rubric v{data.version} · code-owned, deterministic scoring
            </p>
          )}
        </div>
        <IconButton name="x" aria-label="Close" onClick={onClose} />
      </header>

      <div className="flex-1 space-y-6 px-5 py-4">
        {isLoading && <p className="text-body-sm text-text-muted">Loading rubric…</p>}
        {isError && <p className="text-body-sm text-crimson-700">Could not load the rubric.</p>}

        {data && (
          <>
            <section className="space-y-2">
              <MicroCaps as="h3">Scoring rows</MicroCaps>
              <table className="w-full text-body-sm">
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.id} className="border-b border-subtle last:border-0">
                      <td className="py-1.5 pr-3 align-top">
                        {/* A negative support value is a penalty, not a caution,
                            so it reads crimson: amber cannot be text at all
                            (3.77:1), and the negative reading is available. */}
                        <span
                          className={`font-data font-semibold tabular-nums ${
                            row.support_value > 0
                              ? "text-moss-600"
                              : row.support_value < 0
                                ? "text-crimson-700"
                                : "text-text-muted"
                          }`}
                        >
                          {row.support_value > 0 ? `+${row.support_value}` : row.support_value}
                        </span>
                      </td>
                      <td className="py-1.5 align-top">
                        <div className="font-medium text-text-strong">{prettify(row.id)}</div>
                        <div className="text-body-sm text-text-muted">{row.description}</div>
                        {row.note && (
                          <div className="mt-0.5 text-body-sm italic text-text-muted">
                            {row.note}
                          </div>
                        )}
                        {row.cap !== null && (
                          <div className="mt-1">
                            <Badge tone="negative">
                              {row.support_value} per turn · {row.cap} permanent cap
                            </Badge>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {data.combination.length > 0 && (
              <section className="space-y-2">
                <MicroCaps as="h3">How rows combine</MicroCaps>
                <ol className="ml-4 list-decimal space-y-1 text-body-sm text-text-muted">
                  {data.combination.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ol>
              </section>
            )}

            <section className="space-y-3">
              <MicroCaps as="h3">What each concern needs</MicroCaps>
              {/* Inside the white drawer, so `nested` (sand-50) is the fill that
                  reads as a step down. */}
              {data.concerns.map((c) => (
                <Card key={c.concern_id} as="details" nested padding="sm">
                  <summary className="cursor-pointer text-body-sm font-medium text-text-strong">
                    {prettify(c.concern_id)}
                  </summary>
                  <div className="mt-2 space-y-2 text-body-sm text-text-muted">
                    <p>
                      <span className="font-semibold text-text-muted">Core ask: </span>
                      {c.core_ask}
                    </p>
                    <p>
                      <span className="font-semibold text-text-muted">Satisfies: </span>
                      {c.what_would_satisfy}
                    </p>
                    {c.red_lines.length > 0 && (
                      <div>
                        <span className="font-semibold text-crimson-700">Red lines:</span>
                        <ul className="ml-4 list-disc">
                          {c.red_lines.map((rl) => (
                            <li key={rl}>{rl}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </Card>
              ))}
            </section>
          </>
        )}
      </div>
    </Sheet>
  )
}
