// One persona's editable character. Draft state only: the parent owns the
// query, both mutations, and the server's field errors, and re-supplies
// `persona` after every successful save or reset.
//
// `id` and `priorities` are shown for context and are not editable — the
// backend refuses them and the turn order depends on them.

import { useEffect, useState } from "react"

import { prettify } from "../lib"
import type { FieldError, Persona, PersonaUpdate } from "../types"
import { Button } from "./ui/Button"
import { Card } from "./ui/Card"
import { Input } from "./ui/Input"
import { MicroCaps } from "./ui/MicroCaps"
import { Modal } from "./ui/Modal"
import { Select } from "./ui/Select"
import { Textarea } from "./ui/Textarea"

const LINE_FIELDS = [{ key: "display_name", label: "Display name" }] as const
const POLLY_VOICE_IDS = ["Matthew", "Ruth", "Danielle"]

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
    <p role="alert" className="mt-1 text-body-sm font-medium text-crimson-700">
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
      className="space-y-5 border-t border-subtle px-4 py-5"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        onSave(draft)
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {LINE_FIELDS.map((field) => (
          <label key={field.key} className="block">
            <MicroCaps as="span" className="block">
              {field.label}
            </MicroCaps>
            <Input
              data-testid={`field-${field.key}`}
              value={draft[field.key]}
              onChange={(e) => setField(field.key, e.target.value)}
            />
            <FieldMessage message={errorFor(errors, field.key)} />
          </label>
        ))}
        <label className="block">
          <MicroCaps as="span" className="block">
            Polly voice id
          </MicroCaps>
          <Select
            data-testid="field-polly_voice_id"
            value={draft.polly_voice_id}
            onChange={(event) => setField("polly_voice_id", event.target.value)}
          >
            {POLLY_VOICE_IDS.map((voiceId) => (
              <option key={voiceId} value={voiceId}>
                {voiceId}
              </option>
            ))}
          </Select>
          <FieldMessage message={errorFor(errors, "polly_voice_id")} />
        </label>
      </div>

      {BLOCK_FIELDS.map((field) => (
        <label key={field.key} className="block">
          <MicroCaps as="span" className="block">
            {field.label}
          </MicroCaps>
          <Textarea
            rows={3}
            data-testid={`field-${field.key}`}
            value={draft[field.key]}
            onChange={(value) => setField(field.key, value)}
          />
          <FieldMessage message={errorFor(errors, field.key)} />
        </label>
      ))}

      {LIST_FIELDS.map((field) => (
        <fieldset key={field.key} data-testid={`list-${field.key}`}>
          <MicroCaps as="legend">{field.label}</MicroCaps>
          <div className="mt-1 space-y-2">
            {draft[field.key].map((item, i) => (
              // Index keys are correct here: the rows are positional and a row's
              // identity is its position in the authored list.
              <div key={`${field.key}-${i}`} className="flex items-start gap-2">
                <Input
                  aria-label={`${field.label} ${i + 1}`}
                  value={item}
                  onChange={(e) => setListItem(field.key, i, e.target.value)}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  aria-label={`Remove ${field.label.toLowerCase()} ${i + 1}`}
                  onClick={() =>
                    setField(
                      field.key,
                      draft[field.key].filter((_, index) => index !== i),
                    )
                  }
                >
                  Remove
                </Button>
              </div>
            ))}
            <Button
              variant="secondary"
              size="sm"
              data-testid={`add-${field.key}`}
              onClick={() => setField(field.key, [...draft[field.key], ""])}
            >
              Add {field.label.toLowerCase().replace(/s$/, "")}
            </Button>
            <FieldMessage message={errorFor(errors, field.key)} />
          </div>
        </fieldset>
      ))}

      <fieldset data-testid="list-exemplars">
        <MicroCaps as="legend">Exemplars</MicroCaps>
        <div className="mt-1 space-y-3">
          {draft.exemplars.map((exemplar, i) => (
            <Card key={`exemplar-${i}`} nested padding="sm" className="space-y-2">
              {/* Explicit htmlFor/id: the label wraps a component rather than a
                  native control, which the a11y lint cannot see through. */}
              <label className="block" htmlFor={`exemplar-${i}-user`}>
                <MicroCaps as="span" className="block">
                  Answer
                </MicroCaps>
                <Textarea
                  id={`exemplar-${i}-user`}
                  rows={2}
                  value={exemplar.user}
                  onChange={(value) => setExemplar(i, { user: value })}
                />
                <FieldMessage message={errorFor(errors, `exemplars.${i}.user`)} />
              </label>
              <div className="grid gap-2 sm:grid-cols-[8rem_1fr]">
                <p
                  className="block rounded-control border border-subtle bg-sand-200 px-3 py-2 text-body font-semibold text-text-body"
                  data-testid={`exemplar-delta-${i}`}
                >
                  {exemplar.support_delta >= 0 ? "+" : ""}
                  {exemplar.support_delta}
                </p>
                <label className="block" htmlFor={`exemplar-${i}-note`}>
                  <MicroCaps as="span" className="block">
                    Note
                  </MicroCaps>
                  <Input
                    id={`exemplar-${i}-note`}
                    value={exemplar.note}
                    onChange={(e) => setExemplar(i, { note: e.target.value })}
                  />
                  <FieldMessage message={errorFor(errors, `exemplars.${i}.note`)} />
                </label>
              </div>
              <Button
                variant="secondary"
                size="sm"
                aria-label={`Remove exemplar ${i + 1}`}
                onClick={() =>
                  setField(
                    "exemplars",
                    draft.exemplars.filter((_, index) => index !== i),
                  )
                }
              >
                Remove
              </Button>
            </Card>
          ))}
          <Button
            variant="secondary"
            size="sm"
            data-testid="add-exemplar"
            onClick={() =>
              setField("exemplars", [...draft.exemplars, { user: "", support_delta: 0, note: "" }])
            }
          >
            Add exemplar
          </Button>
        </div>
      </fieldset>

      <Card
        as="div"
        nested
        padding="sm"
        className="grid gap-2 text-body-sm text-text-muted sm:grid-cols-2"
      >
        <div>
          <MicroCaps as="dt">Id</MicroCaps>
          <dd data-testid="locked-id">{persona.id}</dd>
        </div>
        <div>
          <MicroCaps as="dt">Priorities</MicroCaps>
          <dd data-testid="locked-priorities">{persona.priorities.map(prettify).join(", ")}</dd>
        </div>
      </Card>

      <div className="flex flex-wrap items-center justify-end gap-3">
        {saved ? <output className="text-body-sm font-medium text-moss-600">Saved</output> : null}
        <Button
          variant="secondary"
          size="sm"
          data-testid={`reset-${persona.id}`}
          disabled={resetting}
          onClick={() => setConfirmingReset(true)}
        >
          Reset to default
        </Button>
        <Button variant="primary" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save persona"}
        </Button>
      </div>

      {/* No `onClose`: the dialog has no dismiss affordance today beyond its own
          "Keep my edits" button, so it must be answered. */}
      <Modal
        open={confirmingReset}
        label={`Reset ${persona.display_name} to the shipped default?`}
        size="sm"
        aria-modal="true"
        data-testid="confirm-reset"
      >
        <h2 className="text-heading font-semibold text-text-strong">
          Reset {persona.display_name} to the shipped default?
        </h2>
        <p className="text-body-sm text-text-muted">
          Every customization to this persona is discarded. This cannot be undone.
        </p>
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            data-testid="confirm-reset-cancel"
            onClick={() => setConfirmingReset(false)}
          >
            Keep my edits
          </Button>
          <Button
            variant="primary"
            data-testid="confirm-reset-confirm"
            onClick={() => {
              setConfirmingReset(false)
              onReset()
            }}
          >
            Reset persona
          </Button>
        </div>
      </Modal>
    </form>
  )
}
