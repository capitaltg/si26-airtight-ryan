import { useState } from "react"

import { PersonaEditor } from "./components/PersonaEditor"
import { Rehearsal } from "./components/Rehearsal"

export default function App() {
  const [view, setView] = useState<"rehearsal" | "personas">("rehearsal")

  if (view === "personas") return <PersonaEditor onClose={() => setView("rehearsal")} />

  return (
    <>
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
    </>
  )
}
