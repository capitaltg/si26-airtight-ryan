import { lazy, Suspense, useState } from "react"

import { PersonaEditor } from "./components/PersonaEditor"
import { Rehearsal } from "./components/Rehearsal"

// Vite statically replaces `import.meta.env.DEV` with `false` in a production
// build, so the ternary folds to `null` and Rollup drops the dynamic import
// entirely — the gallery chunk is not merely unloaded, it is not emitted.
// The gallery stays a dev-only search-param surface: it is the permanent place a
// token or primitive is checked in isolation, not a placeholder for a route.
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
        {/* The persona-editor control lives on the landing screen itself, inside
            its column, rather than in a bar of its own above it. */}
        <Rehearsal onEditPersonas={() => setView("personas")} />
      </div>
      {view === "personas" ? <PersonaEditor onClose={() => setView("rehearsal")} /> : null}
    </>
  )
}
