import { lazy, Suspense, useState } from "react"

import { PersonaEditor } from "./components/PersonaEditor"
import { Rehearsal } from "./components/Rehearsal"
import { Button } from "./components/ui/Button"

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
        <div className="mx-auto flex max-w-3xl justify-end px-4 pt-3">
          <Button
            variant="secondary"
            size="sm"
            data-testid="open-persona-editor"
            onClick={() => setView("personas")}
          >
            Edit personas
          </Button>
        </div>
        <Rehearsal />
      </div>
      {view === "personas" ? <PersonaEditor onClose={() => setView("rehearsal")} /> : null}
    </>
  )
}
