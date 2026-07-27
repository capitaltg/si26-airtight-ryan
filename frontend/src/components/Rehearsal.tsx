// The rehearsal screen: drives one session end to end. It owns session state
// (id, meters, current prompt, done), accumulates the transcript client-side as
// answers are submitted, and exposes the disclosed rubric drawer. All scoring is
// the backend's — this component only renders what the API returns.

import { useEffect, useRef, useState } from "react"
import type { KeyboardEvent, PointerEvent } from "react"

import {
  useAskClarification,
  useCreateSession,
  useSubmitAnswer,
  useSubmitAnswerAudio,
} from "../api/client"
import { playSequence, primePlayback, useRecorder } from "../audio"
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
  // Text is the default and the only path with server tests; the toggle must
  // not change any behavior while left on "text".
  const [mode, setMode] = useState<"text" | "voice">("text")
  // Surfaces a getUserMedia rejection (mic permission denied, no device, etc.)
  // after voice mode auto-falls-back to text — see the recorder.error effect below.
  const [voiceError, setVoiceError] = useState<string | null>(null)

  const create = useCreateSession()
  const submit = useSubmitAnswer(sessionId)
  const clarify = useAskClarification(sessionId)
  const recorder = useRecorder()
  const submitAudio = useSubmitAnswerAudio(sessionId)
  // Guards the hold-to-talk button's pointerup/pointercancel/blur handlers
  // (any of which can fire for a single press-and-release) against submitting
  // more than once per recording, independent of React's state-update timing.
  const recordingActiveRef = useRef(false)
  // `recorder.start()` awaits getUserMedia, so a very quick tap-and-release can
  // fire stopRecording before recording actually begins. Stashing the in-flight
  // start promise lets stopRecording wait for it before deciding whether there's
  // anything to stop.
  const startPromiseRef = useRef<Promise<void> | null>(null)

  const transcriptEndRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [transcript, done, pending, stage])

  // getUserMedia was denied (or failed): voice mode can't work this session,
  // so drop back to text and surface why.
  useEffect(() => {
    if (recorder.error) {
      recordingActiveRef.current = false
      setMode("text")
      setVoiceError(recorder.error)
    }
  }, [recorder.error])

  // Revoke the recorded-answer object URLs on unmount only (not on every
  // transcript change — the turns still reference them for playback until
  // then). A ref tracks the latest transcript so the cleanup closure sees
  // every turn accumulated by the time the presenter navigates away.
  const transcriptRef = useRef<TranscriptTurn[]>(transcript)
  useEffect(() => {
    transcriptRef.current = transcript
  }, [transcript])
  useEffect(() => {
    return () => {
      for (const turn of transcriptRef.current) {
        if (turn.audioUrl) URL.revokeObjectURL(turn.audioUrl)
      }
    }
  }, [])

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
        // Revoke the previous session's recorded-answer object URLs before
        // dropping the transcript that referenced them — the unmount cleanup
        // effect above only fires when the whole component unmounts, so a
        // mid-app "Start a new rehearsal" click needs its own revoke or every
        // restarted session leaks that session's blobs for the tab's life.
        for (const turn of transcriptRef.current) {
          if (turn.audioUrl) URL.revokeObjectURL(turn.audioUrl)
        }
        setSessionId(s.id)
        setMeters(s.meters)
        setPrompt(s.prompt)
        setDone(s.done)
        setTranscript([])
        setShowReport(false)
        setDraft("")
        setMode("text")
        setVoiceError(null)
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

  // Shared hold-to-talk "press" logic, used by both the pointer and keyboard
  // entry points below. Primes the shared playback element (see audio.ts's
  // `primePlayback`) inside this same user gesture so the persona's spoken
  // reply (played back after an async record → upload → score → synthesize
  // round trip, well outside any user gesture) isn't blocked by the browser's
  // autoplay policy.
  function beginRecording() {
    if (recordingActiveRef.current || submitAudio.isPending) return
    recordingActiveRef.current = true
    primePlayback()
    startPromiseRef.current = recorder.start()
  }

  // Hold-to-talk press (pointer). Also captures the pointer on the button
  // itself so a mouse drag off the button before release still delivers
  // pointerup/pointercancel here (touch gets this for free via implicit
  // capture; a plain mouse doesn't).
  function startRecording(e: PointerEvent<HTMLButtonElement>) {
    if (recordingActiveRef.current || submitAudio.isPending) return
    e.currentTarget.setPointerCapture(e.pointerId)
    beginRecording()
  }

  // Hold-to-talk press (keyboard) — Space/Enter while the button is focused.
  // Without this, a keyboard user tabbing to the button and pressing Space or
  // Enter gets an inert `click` event and nothing happens (WCAG 2.1.1).
  // `e.repeat` guards against the OS repeating keydown while the key is held,
  // which would otherwise restart the recording on every repeat event.
  function handleTalkKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== " " && e.key !== "Enter") return
    if (e.key === " ") e.preventDefault() // stop the page from scrolling
    if (e.repeat) return
    beginRecording()
  }

  function handleTalkKeyUp(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== " " && e.key !== "Enter") return
    if (e.key === " ") e.preventDefault()
    stopRecording()
  }

  // Hold-to-talk release. Bound to pointerup/pointercancel/blur (and, for
  // keyboard use, keyup) so a pointer dragged off the button — or a mic left
  // open by an early return — can't leave the mic running (see audio.ts's
  // useRecorder doc comment). Waits for the in-flight start() first (see
  // startPromiseRef) so a fast tap-and-release doesn't race ahead of
  // getUserMedia resolving. `recorder.stop()` runs unconditionally once
  // there's something to stop (guarded only by `recordingActiveRef.current`
  // above); a missing `prompt` only skips building/submitting the turn, since
  // returning early *before* stopping would leave the mic open.
  //
  // `recordingActiveRef.current` is reset only once `recorder.stop()` has
  // resolved and the blob has been handed off (`.finally`, not synchronously
  // at the top): resetting it early would let a second press-and-release
  // landing in that window pass the guard in `beginRecording`, call
  // `recorder.start()` again, and clobber this recording's still-in-flight
  // buffered chunks (audio.ts's `chunksRef` reset) out from under it.
  //
  // Deliberately doesn't gate on `recorder.recording`: that boolean is read
  // from this render's closure over `recorder`, which is frozen at whatever
  // value it had when this particular `stopRecording` instance was created —
  // for a fast tap-and-release it can still read `false` here even after
  // `start()` has finished setting up the recorder, since the state update
  // that would flip it lands in a *later* render's closure, not this one.
  // `recorder.stop()` itself checks a live ref (see audio.ts), so it's the
  // right source of truth for whether there's anything to stop; it resolves
  // with an empty blob when there wasn't, which the size check below catches.
  function stopRecording() {
    if (!recordingActiveRef.current) return
    const asked = prompt // capture the prompt this answer responds to
    const started = startPromiseRef.current ?? Promise.resolve()
    started
      .then(() => recorder.stop())
      .then((blob) => {
        // Nothing was actually recording (e.g. getUserMedia failed, or was
        // still pending, when this press ended) — audio.ts's stop() resolves
        // with an empty blob in that case instead of throwing. Likewise, if
        // there's no active prompt to attach this answer to there's nothing
        // to submit — but the recorder above has already been stopped and the
        // mic released either way.
        if (blob.size === 0 || !asked) return
        // Same optimistic-pending flow as a typed answer, but there's no
        // transcript yet to show, so the placeholder answer is blank.
        setPending({ prompt: asked, answer: "", kind: "answer" })
        setStage("extracting")
        submitAudio.mutate(blob, {
          onSuccess: (res) => {
            setTranscript((prev) => [
              ...prev,
              {
                key: prev.length,
                personaId: res.persona_id,
                concernId: res.concern_id,
                isFollowUp: asked.is_follow_up,
                prompt: asked.prompt,
                answer: res.transcript,
                reply: res.reply,
                rationale: res.rationale,
                supportDelta: res.support_delta,
                matchedRows: res.matched_rows,
                capped: res.capped,
                transcript: res.transcript,
                audioUrl: URL.createObjectURL(blob),
              },
            ])
            setMeters(res.meters)
            setPrompt(res.next_prompt)
            setDone(res.done)
            setPending(null)
            // Play the persona's spoken reply, then the next prompt's spoken
            // read-aloud, back to back. A rejected/blocked clip is swallowed by
            // playSequence itself; the transcript's <audio controls> is the
            // fallback for that case.
            void playSequence(
              [res.reply_audio, res.next_prompt_audio].filter((s): s is string => s != null),
            )
          },
          // Clear the placeholder; submitAudio.isError red text surfaces the
          // message the same way submit.isError does for the text path.
          onError: () => setPending(null),
        })
      })
      .finally(() => {
        recordingActiveRef.current = false
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
            !clarify.isPending &&
            !submitAudio.isPending && (
              <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between gap-2 text-sm">
                  <div className="flex items-center gap-2">
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
                  {/* Text/voice segmented toggle. Text is the default and the
                      only path with server tests; switching to voice never
                      changes text-mode behavior. */}
                  <div className="flex overflow-hidden rounded-md border border-slate-300 text-xs font-semibold">
                    <button
                      type="button"
                      onClick={() => setMode("text")}
                      className={`px-2.5 py-1 transition ${
                        mode === "text"
                          ? "bg-slate-900 text-white"
                          : "bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      Text
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setVoiceError(null)
                        setMode("voice")
                      }}
                      className={`px-2.5 py-1 transition ${
                        mode === "voice"
                          ? "bg-slate-900 text-white"
                          : "bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      Voice
                    </button>
                  </div>
                </div>
                <p className="text-slate-800">{prompt.prompt}</p>
                {voiceError && <p className="text-sm text-red-700">{voiceError}</p>}
                {mode === "text" ? (
                  <>
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
                  </>
                ) : (
                  // Voice mode: hold-to-talk replaces the textarea and both
                  // buttons. "Ask a clarifying question" stays text-only for
                  // now, so it simply isn't offered here.
                  <div className="space-y-2">
                    <button
                      type="button"
                      onPointerDown={startRecording}
                      onPointerUp={stopRecording}
                      onPointerCancel={stopRecording}
                      onBlur={stopRecording}
                      onKeyDown={handleTalkKeyDown}
                      onKeyUp={handleTalkKeyUp}
                      aria-label={
                        recorder.recording
                          ? "Recording your answer — release to send"
                          : "Hold to record your answer"
                      }
                      disabled={submitAudio.isPending}
                      className={`w-full select-none touch-none rounded-lg px-5 py-6 text-sm font-semibold shadow-sm transition disabled:opacity-50 ${
                        recorder.recording
                          ? "bg-red-600 text-white"
                          : "bg-slate-900 text-white hover:bg-slate-700"
                      }`}
                    >
                      {submitAudio.isPending
                        ? "Scoring…"
                        : recorder.recording
                          ? "Recording… release to send"
                          : "Hold to talk"}
                    </button>
                    {submitAudio.isError && (
                      <p className="text-sm text-red-700">{(submitAudio.error as Error).message}</p>
                    )}
                  </div>
                )}
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
