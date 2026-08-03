// One persona's editable character. Draft state only: the parent owns the
// query, both mutations, and the server's field errors, and re-supplies
// `persona` after every successful save or reset.
//
// `id`, `priorities`, and `rubric_version` are shown for context and are not
// editable — the backend refuses them and the turn order depends on them.

import { useEffect, useState } from "react"

import { prettify } from "../lib"
import type { FieldError, Persona, PersonaUpdate } from "../types"

const INPUT =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm"
const LABEL = "block text-xs font-semibold uppercase tracking-wide text-slate-500"
const GHOST_BUTTON =
  "rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
const SOLID_BUTTON =
  "rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:opacity-50"

const LINE_FIELDS = [
  { key: "display_name", label: "Display name" },
  { key: "polly_voice_id", label: "Polly voice id" },
] as const

const BLOCK_FIELDS = [
  { key: "intro", label: "Intro" },
  { key: "voice", label: "Voice" },
  { key: "demographics", label: "Demographics" },
] as const

const LIST_FIELDS = [
  { key: "values", label: "Values" },
  { key: "wants", label: "Wants" },
  { key: "non_negotiables", label: "Non-negotiables" },
] as const

function toDraft(persona: Persona): PersonaUpdate {
  return {
    display_name: persona.display_name,
    intro: persona.intro,
    voice: persona.voice,
    demographics: persona.demographics,
    values: [...persona.values],
    wants: [...persona.wants],
    non_negotiables: [...persona.non_negotiables],
    polly_voice_id: persona.polly_voice_id,
    exemplars: persona.exemplars.map((e) => ({
      user: e.user,
      support_delta: e.support_delta,
      note: e.note,
    })),
  }
}

// 422 locs arrive as ["body", "intro"] / ["body", "exemplars", 0, "note"]. Drop
// the "body" head so a field can look itself up by its own path.
function errorFor(errors: FieldError[], path: string): string | undefined {
  return errors.find((e) => e.loc.slice(1).join(".") === path)?.msg
}

// Named FieldMessage, not FieldError: `FieldError` is the imported 422 type and
// a component of the same name would be a duplicate identifier.
function FieldMessage({ message }: { message: string | undefined }) {
  if (!message) return null
  return (
    <p role="alert" className="mt-1 text-xs font-medium text-red-700">
      {message}
    </p>
  )
}

export function PersonaForm({
  persona,
  errors,
  saving,
  resetting,
  saved,
  onSave,
  onReset,
}: {
  persona: Persona
  errors: FieldError[]
  saving: boolean
  resetting: boolean
  saved: boolean
  onSave: (update: PersonaUpdate) => void
  onReset: () => void
}) {
  const [draft, setDraft] = useState<PersonaUpdate>(() => toDraft(persona))
  const [confirmingReset, setConfirmingReset] = useState(false)

  // A save or reset refetches the list, so the persona prop changes identity;
  // re-seed the draft from the server's copy rather than keeping a stale one.
  useEffect(() => {
    setDraft(toDraft(persona))
  }, [persona])

  function setField<K extends keyof PersonaUpdate>(key: K, value: PersonaUpdate[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function setListItem(key: "values" | "wants" | "non_negotiables", i: number, value: string) {
    setField(
      key,
      draft[key].map((item, index) => (index === i ? value : item)),
    )
  }

  function setExemplar(i: number, patch: Partial<PersonaUpdate["exemplars"][number]>) {
    setField(
      "exemplars",
      draft.exemplars.map((e, index) => (index === i ? { ...e, ...patch } : e)),
    )
  }

  return (
    <form
      data-testid={`persona-form-${persona.id}`}
      className="space-y-5 border-t border-slate-200 px-4 py-5"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        onSave(draft)
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {LINE_FIELDS.map((field) => (
          <label key={field.key} className="block">
            <span className={LABEL}>{field.label}</span>
            <input
              className={INPUT}
              data-testid={`field-${field.key}`}
              value={draft[field.key]}
              onChange={(e) => setField(field.key, e.target.value)}
            />
            <FieldMessage message={errorFor(errors, field.key)} />
          </label>
        ))}
      </div>

      {BLOCK_FIELDS.map((field) => (
        <label key={field.key} className="block">
          <span className={LABEL}>{field.label}</span>
          <textarea
            className={`${INPUT} min-h-[4.5rem]`}
            data-testid={`field-${field.key}`}
            value={draft[field.key]}
            onChange={(e) => setField(field.key, e.target.value)}
          />
          <FieldMessage message={errorFor(errors, field.key)} />
        </label>
      ))}

      {LIST_FIELDS.map((field) => (
        <fieldset key={field.key} data-testid={`list-${field.key}`}>
          <legend className={LABEL}>{field.label}</legend>
          <div className="mt-1 space-y-2">
            {draft[field.key].map((item, i) => (
              // Index keys are correct here: the rows are positional and a row's
              // identity is its position in the authored list.
              <div key={`${field.key}-${i}`} className="flex items-start gap-2">
                <input
                  className={INPUT}
                  aria-label={`${field.label} ${i + 1}`}
                  value={item}
                  onChange={(e) => setListItem(field.key, i, e.target.value)}
                />
                <button
                  type="button"
                  className={GHOST_BUTTON}
                  aria-label={`Remove ${field.label.toLowerCase()} ${i + 1}`}
                  onClick={() =>
                    setField(
                      field.key,
                      draft[field.key].filter((_, index) => index !== i),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            <button
              type="button"
              className={GHOST_BUTTON}
              data-testid={`add-${field.key}`}
              onClick={() => setField(field.key, [...draft[field.key], ""])}
            >
              Add {field.label.toLowerCase().replace(/s$/, "")}
            </button>
            <FieldMessage message={errorFor(errors, field.key)} />
          </div>
        </fieldset>
      ))}

      <fieldset data-testid="list-exemplars">
        <legend className={LABEL}>Exemplars</legend>
        <div className="mt-1 space-y-3">
          {draft.exemplars.map((exemplar, i) => (
            <div key={`exemplar-${i}`} className="space-y-2 rounded-lg bg-slate-50 p-3">
              <label className="block">
                <span className={LABEL}>Answer</span>
                <textarea
                  className={`${INPUT} min-h-[3.5rem]`}
                  value={exemplar.user}
                  onChange={(e) => setExemplar(i, { user: e.target.value })}
                />
                <FieldMessage message={errorFor(errors, `exemplars.${i}.user`)} />
              </label>
              <div className="grid gap-2 sm:grid-cols-[8rem_1fr]">
                <p
                  className="block rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-700"
                  data-testid={`exemplar-delta-${i}`}
                >
                  Score calibration: {exemplar.support_delta >= 0 ? "+" : ""}
                  {exemplar.support_delta} (locked)
                </p>
                <label className="block">
                  <span className={LABEL}>Note</span>
                  <input
                    className={INPUT}
                    value={exemplar.note}
                    onChange={(e) => setExemplar(i, { note: e.target.value })}
                  />
                  <FieldMessage message={errorFor(errors, `exemplars.${i}.note`)} />
                </label>
              </div>
              <button
                type="button"
                className={GHOST_BUTTON}
                aria-label={`Remove exemplar ${i + 1}`}
                onClick={() =>
                  setField(
                    "exemplars",
                    draft.exemplars.filter((_, index) => index !== i),
                  )
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className={GHOST_BUTTON}
            data-testid="add-exemplar"
            onClick={() =>
              setField("exemplars", [...draft.exemplars, { user: "", support_delta: 0, note: "" }])
            }
          >
            Add exemplar
          </button>
        </div>
      </fieldset>

      <dl className="grid gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 sm:grid-cols-3">
        <div>
          <dt className={LABEL}>Id</dt>
          <dd data-testid="locked-id">{persona.id}</dd>
        </div>
        <div>
          <dt className={LABEL}>Priorities</dt>
          <dd data-testid="locked-priorities">{persona.priorities.map(prettify).join(", ")}</dd>
        </div>
        <div>
          <dt className={LABEL}>Rubric version</dt>
          <dd data-testid="locked-rubric-version">{persona.rubric_version}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap items-center justify-end gap-3">
        {saved ? <output className="text-xs font-medium text-emerald-700">Saved</output> : null}
        <button
          type="button"
          className={GHOST_BUTTON}
          data-testid={`reset-${persona.id}`}
          disabled={resetting}
          onClick={() => setConfirmingReset(true)}
        >
          Reset to default
        </button>
        <button type="submit" className={SOLID_BUTTON} disabled={saving}>
          {saving ? "Saving…" : "Save persona"}
        </button>
      </div>

      {confirmingReset ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4">
          {/* Native <dialog open> for the dialog semantics, matching
              DiscardRecordingDialog. */}
          <dialog
            open
            aria-modal="true"
            aria-label={`Reset ${persona.display_name} to the shipped default?`}
            data-testid="confirm-reset"
            className="relative m-0 w-full max-w-sm space-y-3 rounded-lg bg-white p-4 shadow-lg"
          >
            <h2 className="text-sm font-semibold text-slate-800">
              Reset {persona.display_name} to the shipped default?
            </h2>
            <p className="text-xs text-slate-600">
              Every customization to this persona is discarded. This cannot be undone.
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                className={GHOST_BUTTON}
                data-testid="confirm-reset-cancel"
                onClick={() => setConfirmingReset(false)}
              >
                Keep my edits
              </button>
              <button
                type="button"
                className={SOLID_BUTTON}
                data-testid="confirm-reset-confirm"
                onClick={() => {
                  setConfirmingReset(false)
                  onReset()
                }}
              >
                Reset persona
              </button>
            </div>
          </dialog>
        </div>
      ) : null}
    </form>
  )
}
