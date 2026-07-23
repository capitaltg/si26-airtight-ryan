// The rehearsal screen: drives one session end to end. It owns session state
// (id, meters, current prompt, done), accumulates the transcript client-side as
// answers are submitted, and exposes the disclosed rubric drawer. All scoring is
// the backend's — this component only renders what the API returns.

import { useEffect, useRef, useState } from "react"

import { useAskClarification, useCreateSession, useSubmitAnswer } from "../api/client"
import { prettify } from "../lib"
import type { Meter, Prompt, Stage, TranscriptTurn } from "../types"
import { AfterActionReport } from "./AfterActionReport"
import { ChatTurn } from "./ChatTurn"
import { MeterPanel } from "./MeterBar"
import { PendingTurn } from "./PendingTurn"
import { RubricPanel } from "./RubricPanel"

export function Rehearsal() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [meters, setMeters] = useState<Meter[]>([])
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([])
  const [done, setDone] = useState(false)
  const [draft, setDraft] = useState("")
  const [rubricOpen, setRubricOpen] = useState(false)
  const [showReport, setShowReport] = useState(false)
  // Optimistic pending turn: the submitted answer + which prompt it answered,
  // shown with a live stage stepper while the backend scores it.
  const [pending, setPending] = useState<{
    prompt: Prompt
    answer: string
    kind: "answer" | "clarify"
  } | null>(null)
  const [stage, setStage] = useState<Stage>("extracting")
  const [elapsed, setElapsed] = useState(0)
  // Clarifications left on the current concern. null = not yet asked (full
  // allowance); reset whenever the active concern changes.
  const [clarifyRemaining, setClarifyRemaining] = useState<number | null>(null)

  const create = useCreateSession()
  const submit = useSubmitAnswer(sessionId)
  const clarify = useAskClarification(sessionId)

  const transcriptEndRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [transcript, done, pending, stage])

  // A new concern gets a fresh clarification allowance; drop the stale counter
  // when the active prompt moves to a different concern.
  useEffect(() => {
    setClarifyRemaining(null)
  }, [prompt?.concern_id])

  // Elapsed-seconds clock: runs only while a turn is pending, reset on each start.
  useEffect(() => {
    if (!pending) return
    setElapsed(0)
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [pending])

  function startSession() {
    create.mutate(undefined, {
      onSuccess: (s) => {
        setSessionId(s.id)
        setMeters(s.meters)
        setPrompt(s.prompt)
        setDone(s.done)
        setTranscript([])
        setShowReport(false)
        setDraft("")
      },
    })
  }

  // Shared "start over" control. Used on the done panel and the after-action
  // report header so both share one definition of label / disabled / error.
  function renderRetryButton(className: string) {
    return (
      <button onClick={startSession} disabled={create.isPending} className={className}>
        {create.isPending ? "Starting…" : "Start a new rehearsal"}
      </button>
    )
  }

  function sendAnswer() {
    const answer = draft.trim()
    if (!answer || !prompt || submit.isPending) return
    const asked = prompt // capture the prompt this answer responds to
    // Show the answer immediately with a stepper starting at the first stage;
    // `onStage` advances it as the SSE stream reports each pipeline boundary.
    setPending({ prompt: asked, answer, kind: "answer" })
    setStage("extracting")
    submit.mutate(
      { answer, onStage: setStage },
      {
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
          setPending(null)
        },
        // Clear the placeholder; the existing submit.isError red text surfaces
        // the message and the presenter retries with the draft still intact.
        onError: () => setPending(null),
      },
    )
  }

  function sendClarification() {
    const question = draft.trim()
    if (!question || !prompt || clarify.isPending || clarifyRemaining === 0) return
    const asked = prompt
    // Same optimistic placeholder as a scored answer: the question lands
    // immediately with a live spinner while the evaluator replies.
    setPending({ prompt: asked, answer: question, kind: "clarify" })
    clarify.mutate(question, {
      onSuccess: (res) => {
        // Append the exchange marked not scored. Deliberately do NOT touch
        // meters, prompt, or done: the meter is unmoved and the same prompt
        // stays active, so the presenter still owes a real answer.
        setTranscript((prev) => [
          ...prev,
          {
            key: prev.length,
            personaId: res.persona_id,
            concernId: res.concern_id,
            isFollowUp: asked.is_follow_up,
            prompt: asked.prompt,
            answer: question,
            reply: res.reply,
            rationale: "",
            supportDelta: 0,
            matchedRows: [],
            capped: false,
            scored: false,
          },
        ])
        setClarifyRemaining(res.remaining)
        setDraft("")
        setPending(null)
      },
      // Clear the placeholder; clarify.isError red text surfaces the message and
      // the draft stays intact for a retry.
      onError: () => setPending(null),
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

  // Session finished and the presenter asked to see the report: hand the whole
  // screen to the after-action report.
  if (done && showReport && sessionId) {
    return (
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-4 px-4 py-6">
        <div className="flex items-center justify-between print:hidden">
          <button
            onClick={() => setShowReport(false)}
            className="text-sm font-medium text-slate-500 hover:text-slate-800"
          >
            ← Back to transcript
          </button>
          {renderRetryButton(
            "rounded-lg border border-slate-300 bg-white px-4 py-1.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50",
          )}
        </div>
        {create.isError && (
          <p className="text-sm text-red-700 print:hidden">{(create.error as Error).message}</p>
        )}
        <AfterActionReport sessionId={sessionId} />
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Airtight rehearsal</h1>
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
            {transcript.length === 0 && !pending && !done && (
              <p className="text-sm text-slate-400">
                Your answers and each evaluator&apos;s reply will appear here.
              </p>
            )}
            {transcript.map((turn) => (
              <ChatTurn key={turn.key} turn={turn} />
            ))}
            {pending && (
              <PendingTurn
                prompt={pending.prompt}
                answer={pending.answer}
                stage={stage}
                elapsed={elapsed}
                kind={pending.kind}
              />
            )}
            <div ref={transcriptEndRef} />
          </div>

          {done ? (
            <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-center text-sm text-emerald-800">
              <p>Rehearsal complete. Every concern has been covered.</p>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={() => {
                    create.reset() // drop any stale retry error before leaving this panel
                    setShowReport(true)
                  }}
                  className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700"
                >
                  View after-action report
                </button>
                {renderRetryButton(
                  "rounded-lg border border-emerald-300 bg-white px-5 py-2 text-sm font-semibold text-emerald-800 shadow-sm transition hover:bg-emerald-100 disabled:opacity-50",
                )}
              </div>
              {create.isError && (
                <p className="text-sm text-red-700">{(create.error as Error).message}</p>
              )}
            </div>
          ) : (
            // Hidden while a turn is pending (scored answer or clarification):
            // the pending turn in the transcript carries the live spinner, so the
            // input box would only duplicate the wait.
            prompt &&
            !submit.isPending &&
            !clarify.isPending && (
              <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-semibold text-slate-800">
                    {prettify(prompt.persona_id)}
                  </span>
                  <span className="text-slate-400">·</span>
                  <span className="text-slate-500">{prettify(prompt.concern_id)}</span>
                  {prompt.is_follow_up && (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700">
                      Follow-up
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
                  disabled={submit.isPending || clarify.isPending}
                />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm">
                    {submit.isError ? (
                      <span className="text-red-700">{(submit.error as Error).message}</span>
                    ) : clarify.isError ? (
                      <span className="text-red-700">{(clarify.error as Error).message}</span>
                    ) : clarifyRemaining === 0 ? (
                      <span className="text-slate-400">
                        No clarifications left on this concern.
                      </span>
                    ) : null}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={sendClarification}
                      disabled={
                        submit.isPending ||
                        clarify.isPending ||
                        clarifyRemaining === 0 ||
                        !draft.trim()
                      }
                      title="Ask the evaluator what they mean, without being scored"
                      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
                    >
                      {clarify.isPending ? "Asking…" : "Ask a clarifying question"}
                    </button>
                    <button
                      onClick={sendAnswer}
                      disabled={submit.isPending || clarify.isPending || !draft.trim()}
                      className="rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:opacity-50"
                    >
                      {submit.isPending ? "Scoring…" : "Submit"}
                    </button>
                  </div>
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
