// "How you're scored" drawer — the disclosed rubric (spec: the rubric is shown,
// not hidden). A shadcn `Sheet`-style slide-in built with Tailwind: an overlay
// plus a right-anchored panel, closed on backdrop click or Escape.

import { useEffect } from "react"

import { useRubric } from "../api/client"
import { prettify } from "../lib"

export function RubricPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data, isLoading, isError } = useRubric()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} aria-hidden="true" />
      <dialog
        open
        aria-label="How you're scored"
        className="relative m-0 flex h-full w-full max-w-md flex-col overflow-y-auto bg-white p-0 text-slate-900 shadow-xl"
      >
        <header className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">How you&apos;re scored</h2>
            {data && (
              <p className="text-xs text-slate-500">
                Rubric v{data.version} · red line pins support at ≤ {data.cap_ceiling}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="flex-1 space-y-6 px-5 py-4">
          {isLoading && <p className="text-sm text-slate-500">Loading rubric…</p>}
          {isError && <p className="text-sm text-red-700">Could not load the rubric.</p>}

          {data && (
            <>
              <section className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Scoring rows
                </h3>
                <table className="w-full text-sm">
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={row.id} className="border-b border-slate-100 last:border-0">
                        <td className="py-1.5 pr-3 align-top">
                          <span
                            className={`tabular-nums font-semibold ${
                              row.support_value > 0
                                ? "text-emerald-700"
                                : row.support_value < 0
                                  ? "text-orange-700"
                                  : "text-slate-500"
                            }`}
                          >
                            {row.support_value > 0 ? `+${row.support_value}` : row.support_value}
                          </span>
                        </td>
                        <td className="py-1.5 align-top">
                          <div className="font-medium text-slate-800">{prettify(row.id)}</div>
                          <div className="text-xs text-slate-500">{row.description}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  What each concern needs
                </h3>
                {data.concerns.map((c) => (
                  <details
                    key={c.concern_id}
                    className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
                  >
                    <summary className="cursor-pointer text-sm font-medium text-slate-800">
                      {prettify(c.concern_id)}
                    </summary>
                    <div className="mt-2 space-y-2 text-xs text-slate-600">
                      <p>
                        <span className="font-semibold text-slate-500">Core ask: </span>
                        {c.core_ask}
                      </p>
                      <p>
                        <span className="font-semibold text-slate-500">Satisfies: </span>
                        {c.what_would_satisfy}
                      </p>
                      {c.red_lines.length > 0 && (
                        <div>
                          <span className="font-semibold text-red-600">Red lines:</span>
                          <ul className="ml-4 list-disc">
                            {c.red_lines.map((rl) => (
                              <li key={rl}>{rl}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </details>
                ))}
              </section>
            </>
          )}
        </div>
      </dialog>
    </div>
  )
}
