import { lazy, Suspense, useState } from "react"

import { PersonaEditor } from "./components/PersonaEditor"
import { Rehearsal } from "./components/Rehearsal"

// Vite statically replaces `import.meta.env.DEV` with `false` in a production
// build, so the ternary folds to `null` and Rollup drops the dynamic import
// entirely — the gallery chunk is not merely unloaded, it is not emitted.
// SP2 converts this to a real route once react-router lands.
const Gallery = import.meta.env.DEV ? lazy(() => import("./components/Gallery")) : null

export default function App() {
  const [view, setView] = useState<"rehearsal" | "personas">("rehearsal")

  if (Gallery && new URLSearchParams(window.location.search).has("gallery")) {
    return (
      <Suspense fallback={null}>
        <Gallery />
      </Suspense>
    )
  }

  return (
    <>
      <div hidden={view !== "rehearsal"}>
        <div className="mx-auto flex max-w-3xl justify-end px-4 pt-3">
          <button
            type="button"
            data-testid="open-persona-editor"
            onClick={() => setView("personas")}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            Edit personas
          </button>
        </div>
        <Rehearsal />
      </div>
      {view === "personas" ? <PersonaEditor onClose={() => setView("rehearsal")} /> : null}
    </>
  )
}
