// The persona editor screen: reskin the three shipped evaluators, or put one
// back the way it came. Owns the query and both mutations; PersonaForm owns the
// draft for whichever persona is expanded.
//
// The three personas are fixed — there is no add or remove. Their ids,
// priorities, and rubric version are what give each of the eight concerns
// exactly one owner, so those fields are read-only here and refused by the API.

import { useState } from "react"

import { ApiValidationError, usePersonas, useResetPersona, useSavePersona } from "../api/client"
import { prettify } from "../lib"
import type { PersonaUpdate } from "../types"
import { PersonaAvatar } from "./PersonaAvatar"
import { PersonaForm } from "./PersonaForm"

export function PersonaEditor({ onClose }: { onClose: () => void }) {
  const personas = usePersonas()
  const save = useSavePersona()
  const reset = useResetPersona()
  const [openId, setOpenId] = useState<string | null>(null)

  // A 422 renders inline against its fields; anything else (write failed, disk
  // full, reload blew up) is a banner, because no single field explains it.
  const fieldErrors = save.error instanceof ApiValidationError ? save.error.fieldErrors : []
  const bannerError =
    save.error && !(save.error instanceof ApiValidationError)
      ? save.error.message
      : (reset.error?.message ?? null)

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-slate-800">Personas</h1>
        <button
          type="button"
          data-testid="close-persona-editor"
          onClick={onClose}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
        >
          Back to rehearsal
        </button>
      </header>

      <p className="text-sm text-slate-600">
        Edit how each evaluator sounds and what they reward. Changes apply to the next question
        asked; a rehearsal already under way keeps the persona it started with.
      </p>

      {bannerError ? (
        <p
          role="alert"
          data-testid="persona-editor-error"
          className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800"
        >
          {bannerError}
        </p>
      ) : null}

      {personas.isPending ? <p className="text-sm text-slate-600">Loading personas…</p> : null}
      {personas.error ? (
        <p role="alert" className="text-sm font-medium text-red-800">
          {personas.error.message}
        </p>
      ) : null}

      <ul className="space-y-3">
        {(personas.data ?? []).map((persona) => {
          const open = openId === persona.id
          const busySaving = save.isPending && save.variables?.id === persona.id
          const busyResetting = reset.isPending && reset.variables === persona.id
          const mine = save.variables?.id === persona.id
          return (
            <li
              key={persona.id}
              data-testid={`persona-row-${persona.id}`}
              className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
            >
              <button
                type="button"
                data-testid={`toggle-${persona.id}`}
                aria-expanded={open}
                onClick={() => setOpenId(open ? null : persona.id)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-slate-50"
              >
                <PersonaAvatar personaId={persona.id} size={32} />
                <span className="flex-1">
                  <span className="block text-sm font-semibold text-slate-800">
                    {persona.display_name}, {prettify(persona.id)}
                  </span>
                  <span className="block text-xs text-slate-500">
                    {persona.priorities.map(prettify).join(" · ")}
                  </span>
                </span>
                {persona.is_customized ? (
                  <span
                    data-testid={`customized-${persona.id}`}
                    className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900"
                  >
                    Customized
                  </span>
                ) : null}
                <span aria-hidden="true" className="text-slate-400">
                  {open ? "−" : "+"}
                </span>
              </button>

              {open ? (
                <PersonaForm
                  persona={persona}
                  errors={mine ? fieldErrors : []}
                  saving={busySaving}
                  resetting={busyResetting}
                  saved={save.isSuccess && mine}
                  onSave={(update: PersonaUpdate) => {
                    save.reset()
                    save.mutate({ id: persona.id, update })
                  }}
                  onReset={() => {
                    reset.reset()
                    reset.mutate(persona.id)
                  }}
                />
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
