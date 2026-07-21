// The rehearsal screen: drives one session end to end. It owns session state
// (id, meters, current prompt, done), accumulates the transcript client-side as
// answers are submitted, and exposes the disclosed rubric drawer. All scoring is
// the backend's — this component only renders what the API returns.

import { useEffect, useRef, useState } from "react"

import { useCreateSession, useSubmitAnswer } from "../api/client"
import { prettify } from "../lib"
import type { Meter, Prompt, TranscriptTurn } from "../types"
import { ChatTurn } from "./ChatTurn"
import { MeterPanel } from "./MeterBar"
import { RubricPanel } from "./RubricPanel"

export function Rehearsal() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [meters, setMeters] = useState<Meter[]>([])
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([])
  const [done, setDone] = useState(false)
  const [draft, setDraft] = useState("")
  const [rubricOpen, setRubricOpen] = useState(false)

  const create = useCreateSession()
  const submit = useSubmitAnswer(sessionId)

  const transcriptEndRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [transcript, done])

  function startSession() {
    create.mutate(undefined, {
      onSuccess: (s) => {
        setSessionId(s.id)
        setMeters(s.meters)
        setPrompt(s.prompt)
        setDone(s.done)
        setTranscript([])
      },
    })
  }

  function sendAnswer() {
    const answer = draft.trim()
    if (!answer || !prompt || submit.isPending) return
    const asked = prompt // capture the prompt this answer responds to
    submit.mutate(answer, {
      onSuccess: (res) => {
        setTranscript((prev) => [
          ...prev,
          {
            key: prev.length,
            personaId: res.persona_id,
            concernId: res.concern_id,
            isFollowUp: asked.is_follow_up,
            prompt: asked.prompt,
            answer,
            reply: res.reply,
            rationale: res.rationale,
            supportDelta: res.support_delta,
            matchedRows: res.matched_rows,
            capped: res.capped,
          },
        ])
        setMeters(res.meters)
        setPrompt(res.next_prompt)
        setDone(res.done)
        setDraft("")
      },
    })
  }

  // Not started yet: a single call to action.
  if (!sessionId) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 px-6 text-center">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">Airtight</h1>
          <p className="max-w-md text-slate-500">
            Rehearse a federal-orals evaluation. Answer three evaluator personas; every turn earns a
            deterministic, code-owned score.
          </p>
        </div>
        <button
          onClick={startSession}
          disabled={create.isPending}
          className="rounded-lg bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:opacity-50"
        >
          {create.isPending ? "Starting…" : "Start rehearsal"}
        </button>
        {create.isError && (
          <p className="text-sm text-red-700">{(create.error as Error).message}</p>
        )}
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Airtight — rehearsal</h1>
        <button
          onClick={() => setRubricOpen(true)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          How you&apos;re scored
        </button>
      </header>

      <div className="grid gap-4 md:grid-cols-[1fr_18rem]">
        {/* transcript + input */}
        <div className="flex flex-col gap-4">
          <div className="flex-1 space-y-4 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-4">
            {transcript.length === 0 && !done && (
              <p className="text-sm text-slate-400">
                Your answers and each evaluator&apos;s reply will appear here.
              </p>
            )}
            {transcript.map((turn) => (
              <ChatTurn key={turn.key} turn={turn} />
            ))}
            <div ref={transcriptEndRef} />
          </div>

          {done ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-center text-sm text-emerald-800">
              Rehearsal complete — every concern has been covered. The after-action report is next.
            </div>
          ) : (
            prompt && (
              <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-semibold text-slate-800">
                    {prettify(prompt.persona_id)}
                  </span>
                  <span className="text-slate-400">·</span>
                  <span className="text-slate-500">{prettify(prompt.concern_id)}</span>
                  {prompt.is_follow_up && (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700">
                      follow-up
                    </span>
                  )}
                </div>
                <p className="text-slate-800">{prompt.prompt}</p>
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) sendAnswer()
                  }}
                  rows={4}
                  placeholder="Your answer… (⌘/Ctrl+Enter to submit)"
                  className="w-full resize-y rounded-md border border-slate-300 p-3 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
                  disabled={submit.isPending}
                />
                <div className="flex items-center justify-between">
                  {submit.isError ? (
                    <span className="text-sm text-red-700">{(submit.error as Error).message}</span>
                  ) : (
                    <span />
                  )}
                  <button
                    onClick={sendAnswer}
                    disabled={submit.isPending || !draft.trim()}
                    className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:opacity-50"
                  >
                    {submit.isPending ? "Scoring…" : "Submit"}
                  </button>
                </div>
              </div>
            )
          )}
        </div>

        {/* meters */}
        <div className="md:sticky md:top-6 md:self-start">
          <MeterPanel meters={meters} />
        </div>
      </div>

      <RubricPanel open={rubricOpen} onClose={() => setRubricOpen(false)} />
    </div>
  )
}
