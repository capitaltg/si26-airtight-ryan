# Cancel microphone input mid-recording — design

Date: 2026-07-30
Status: proposed

## 1. Context

Voice mode is one-way today. `stopRecording` (`frontend/src/components/Rehearsal.tsx:445`) always hands the recorded blob to `transcribeAudio.mutate`, so releasing the hold-to-talk button is the same event as committing the take. There is no abort path anywhere: a grep for `AbortController` across `frontend/src` and `e2e/tests` returns zero hits, and no fetch in the app is cancellable.

`2026-07-30-editable-voice-transcript-design.md:21` made that explicit — "Exits from the review card: **Submit only.** No re-record, no discard" — on the reasoning that the delivery is committed the instant the button is released.

That reasoning still holds for a *completed* take. It does not hold for one that is still in progress. A presenter who fumbles a sentence, is interrupted, or starts talking before they are ready currently has to let a dead take run all the way through transcription and the review card before they can do anything with it.

This design adds a cancel path for the recording window only. The presenter can abandon a take while the mic is live, or while transcription is still in flight, and then answer the same question again in either text or voice. The review card stays submit-only: once a transcript is on screen, the one-delivery-per-prompt rule is unchanged.

Nothing is written server-side by a cancelled take. `transcribe_audio` (`server/app/api/sessions.py:457`) is read-only and never touches the DB, and `answer_audio` is never reached. **This is a frontend-only change.**

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| What is cancellable | Mid-recording and mid-transcription. Not the review card. | Those two states hold no committed delivery. Discarding from the review card is a retake under another name — the exact thing the previous spec ruled out. |
| Triggers | Escape key and a Cancel button. | Escape is the only trigger that works during a pointer hold (see 5.4). The button is the discoverable path for Space push-to-talk and for the transcribing state. |
| Confirmed or immediate | Confirmed, with a dialog. | The presenter has already spoken. A stray Escape should not silently destroy a good take. |
| Mic while the dialog is up | Recorder stops **before** the dialog opens. | A live mic behind a modal is wrong regardless of what the presenter picks, and the browser's mic-in-use indicator would stay lit. |
| The non-destructive branch | "Use recording" — falls through to the normal transcribe + review flow. | A `MediaRecorder` cannot cleanly resume after `stop()`, and the presenter's finger is already off the button, so "resume recording" is not implementable. Keeping the take is the honest opposite of discarding it. |
| State after discard | Idle, same prompt, still in voice mode. No prompt-audio replay. | The question never changed. Re-speaking it would punish the presenter for cancelling. |
| Tangent limit | Cancelled audio is never measured. | Duration is measured server-side in `answer_audio` (`server/app/api/sessions.py:525`), which a cancelled take never reaches. Nothing to exempt. |

## 3. Flow

```
recording (mic live)
  |
  | Escape, or Cancel button (Space push-to-talk / non-pointer holds)
  v
recorder.stop() -> blob held in state, tracks released, mic indicator off
  |
  +-- blob.size === 0 --> straight back to idle, no dialog
  |
  v
+------------------------------------------+
| Discard this recording?                  |
| You'll answer this question again.       |
|   [ Use recording ]   [ Discard take ]   |
+------------------------------------------+
       |                        |
       v                        v
  transcribe + review      blob dropped -> idle, same prompt, voice mode


transcribing (transcribe_audio in flight)
  |
  | Escape, or Cancel button
  v
+------------------------------------------+
| Discard this recording?                  |
| You'll answer this question again.       |
|   [ Keep waiting ]    [ Discard take ]   |
+------------------------------------------+
       |                        |
       v                        v
  dialog closes, request     controller.abort() + transcribeAudio.reset()
  keeps running              -> idle, same prompt, voice mode
```

Escape pressed *on the dialog* takes the non-destructive branch (Use recording / Keep waiting), matching normal dialog-dismiss semantics.

## 4. Backend

None. `transcribe_audio` stays read-only, `answer_audio` is untouched, no migration, no new endpoint. An aborted upload only detaches the client — the server may still finish the Amazon Transcribe call and be billed for it, which is acceptable because no state is written either way.

## 5. Frontend

### 5.1 New component: `frontend/src/components/DiscardRecordingDialog.tsx`

Presentational, props-in/callbacks-out, in the shape of `VoiceReview.tsx:7`.

```ts
type Props = {
  kind: "recording" | "transcribing"
  onKeep: () => void
  onDiscard: () => void
}
```

`kind` picks the keep-button label ("Use recording" / "Keep waiting"); everything else is shared. Markup copies the native `<dialog open aria-modal="true">` inside a fixed backdrop from the mic-check modal at `Rehearsal.tsx:996-1017` — that pattern was chosen to satisfy oxlint's jsx-a11y `prefer-tag-over-role` rule without a suppression, and the comment at `:997-1000` records why. Discard takes the primary button classes (`Rehearsal.tsx:905`), keep takes the secondary/outline classes (`:893`). Test ids: `discard-recording`, `discard-recording-keep`, `discard-recording-discard`.

### 5.2 `Rehearsal.tsx` — splitting the blob handoff

Extract the body of the `.then((blob) => ...)` at `:452-477` into `handleRecordedBlob(blob, asked)`, verbatim. `stopRecording` keeps its current shape and calls it; the cancel path calls it only when the presenter picks "Use recording".

Everything in `:419-486` stays as-is — the `startPromiseRef` await, the deliberate non-gating on `recorder.recording`, the `.finally` reset ordering. That block encodes several already-fixed races (commits `baa3797`, `ad13d28`, `75ec239`) and must not be rewritten while adding this feature.

### 5.3 `Rehearsal.tsx` — cancel state

```ts
type DiscardPrompt =
  | { kind: "recording"; blob: Blob; asked: Prompt }
  | { kind: "transcribing" }

const [discardPrompt, setDiscardPrompt] = useState<DiscardPrompt | null>(null)
const cancelIntentRef = useRef(false)
const transcribeAbortRef = useRef<AbortController | null>(null)
```

Cancel intent travels through a **ref, not a parameter**. `stopRecording` is reachable from `pointerup`, `pointercancel`, `blur`, `keyup`, and the push-to-talk effect cleanup (`:610`), any of which can fire for one press. This matches the re-entrancy convention already documented at `:121-141`. A trailing `pointerup` after Escape is already a no-op: either `stopInFlightRef` is set or `recordingActiveRef` is already cleared.

Handlers:

- `cancelRecording()` — set `cancelIntentRef.current = true`, call `stopRecording()`. The tail reads and clears the ref, then routes a non-empty blob to `setDiscardPrompt({ kind: "recording", blob, asked })` instead of `handleRecordedBlob`.
- `cancelTranscription()` — `setDiscardPrompt({ kind: "transcribing" })`. Does not abort yet; the dialog decides.
- `keepDiscardPrompt()` — recording variant calls `handleRecordedBlob(blob, asked)`; transcribing variant just closes. Clears `discardPrompt`.
- `discardTake()` — transcribing variant calls `transcribeAbortRef.current?.abort()` then `transcribeAudio.reset()`. Both variants clear `discardPrompt`, set `voiceAnswerLockedRef.current = false`, and leave `prompt`, `mode`, and `review` untouched.

`transcribeAudio.reset()` is **mandatory**. `Rehearsal.tsx:976-978` renders `transcribeAudio.error` to the presenter, so without a reset a discard during transcription prints "The user aborted a request." as if something broke.

`recordingElapsed` resets on its own through the effect at `:197`.

### 5.4 `Rehearsal.tsx` — triggers and lock

`voiceAnswerLocked` (`:103`) gains one term:

```ts
const voiceAnswerLocked =
  transcribeAudio.isPending || submitAudio.isPending || review !== null || discardPrompt !== null
```

That single change disables the Text/Voice toggle, the mic-check button, the textarea, and `pushToTalkEnabled` (`:571`) while the dialog is up — the same reason `micCheckOpen` gates push-to-talk. `voiceAnswerLockedRef` follows through its existing effect at `:118`, which also keeps the stale-prompt-audio suppression at `:362-374` correct.

Escape listener registered only while `(recorder.recording || transcribeAudio.isPending || discardPrompt !== null) && !micCheckOpen`, mirroring the mic-check listener at `:616-623`. With the dialog open it takes the keep branch.

Cancel button rendered next to hold-to-talk while `recorder.recording || transcribeAudio.isPending`, secondary styling, `aria-label` naming the action.

**Pointer-capture limitation, documented in a comment rather than worked around.** `startRecording` calls `setPointerCapture` (`:397`), so during a mouse or touch hold every pointer event routes to the talk button and releasing anywhere submits — the Cancel button is unreachable in that state. Escape covers all four cases; the button covers Space push-to-talk holds and the transcribing state. Hijacking pointer capture to make a second button clickable mid-hold would put the release races at `:419-444` back in play.

`startSession.onSuccess` (`:212-234`) must also clear `discardPrompt`, alongside its existing `setReview(null)` and `voiceAnswerLockedRef` reset.

### 5.5 API client

Thread an optional `AbortSignal` through `postMultipart` (`frontend/src/api/client.ts:96`), `api.transcribeAudio` (`:128`), and `useTranscribeAudio` (`:195`) — the mutation's variables become `{ blob, signal }` instead of a bare `Blob`. One call site to update (`Rehearsal.tsx:463`).

`useSubmitAnswerAudio` is untouched. Submission is not cancellable.

### 5.6 Untouched

`useRecorder` (`frontend/src/audio.ts:49`) needs no change — `stop()` already runs `releaseStream()` in `onstop` (`:101`), so cancel needs no new mic-release code. `primePlayback` is not re-called on cancel; the element stays unlocked from the original `beginRecording`. `VoiceReview.tsx` and `ChatTurn.tsx` are untouched.

## 6. Errors and edge cases

- **Empty blob** — cancel before getUserMedia resolves, or an instant tap-cancel: `blob.size === 0` skips the dialog and returns to idle. Same check the submit path already makes at `:459`.
- **Mic denied mid-flow** — the `recorder.error` effect at `:150` still drops to text mode. Its `if (!voiceAnswerLocked)` guard picks up the open dialog for free via the lock change in 5.4.
- **Transcribe resolves while the transcribing dialog is open** — `onSuccess` sets `review`, the "Transcribing…" state ends, and the dialog is now stale. Close it in an effect when `transcribeAudio.isPending` goes false while `discardPrompt?.kind === "transcribing"`, taking the keep branch: the transcript exists and the review card owns the screen.
- **Aborted request still runs server-side** — `abort()` only detaches the client. Acceptable; no state is written.
- **Escape while the mic-check modal is open** belongs to the mic check. The new listener is gated on `!micCheckOpen`.
- **No object URL to clean up** — `URL.createObjectURL` runs only in `submitReview`'s `onSuccess` (`:525`). A discarded blob is released by dropping the state.

## 7. Test plan

Repo convention is TDD (`AGENTS.md:5-13`), failing test first. There is no frontend unit-test runner in this repo (no vitest, jest, or testing-library anywhere), so Playwright is the test layer.

New spec `e2e/tests/cancel-recording.spec.ts`, registered in the `MIC_SPEC` regex at `e2e/playwright.config.ts:11` so it runs under the fake-media project. Easy to forget; without it the spec runs with no microphone.

Reuse `stubVoiceRoutes` / `openVoiceMode` / `recordAnswer` from `voice-transcript-edit.spec.ts:44-91`, extended with a `transcribeDelayMs` option so the transcribing state can be held open.

1. Escape mid-recording opens the dialog and `transcribeCalls` stays 0 (`expect.poll`, the pattern at `voice-transcript-edit.spec.ts:139-152`).
2. "Discard take" returns to "Hold to talk", the prompt text is unchanged, and both `transcribeCalls` and `answerAudioCalls` are 0.
3. "Use recording" produces the normal review card and exactly one `transcribeCalls`.
4. With a delayed transcribe stub, the Cancel button during "Transcribing…" opens the dialog; "Discard take" returns to idle with no review card, no `answer_audio` call, and **no error text on screen** — the regression guard for a missing `reset()`.
5. While the dialog is open, the Text/Voice toggle and mic-check button are disabled and Space does not start a new recording.
6. After discarding, answering the same prompt again works end to end — once in voice, once by toggling to Text and submitting.
7. `voice-transcript-edit.spec.ts` and `voice-prompt-audio.spec.ts` still pass unchanged.

Manual, real mic: hold to talk, press Escape, confirm the browser's mic-in-use indicator goes off *before* the dialog is answered, and that "Discard take" leaves the OS mic released.

## 8. Non-goals

- Discarding or re-recording from the review card. `2026-07-30-editable-voice-transcript-design.md:21` still governs there: once a transcript is on screen the presenter edits and submits it.
- Cancelling a submission in flight (`answer_audio`). Once scoring starts the turn is committed.
- Pausing and resuming a recording.
- Cancelling a text answer. The textarea already keeps its draft.
- Any server-side change.

## 9. Files

| File | Change |
|---|---|
| `frontend/src/components/DiscardRecordingDialog.tsx` | New. Confirm dialog, two label variants. |
| `frontend/src/components/Rehearsal.tsx` | `discardPrompt` state, `cancelIntentRef`, `transcribeAbortRef`; extract `handleRecordedBlob`; `cancelRecording` / `cancelTranscription` / `keepDiscardPrompt` / `discardTake`; extend `voiceAnswerLocked` (`:103`); Escape effect; Cancel button near `:948-975`; render the dialog beside the mic-check modal; clear `discardPrompt` in `startSession.onSuccess`. |
| `frontend/src/api/client.ts` | Optional `AbortSignal` through `postMultipart` (`:96`), `transcribeAudio` (`:128`), `useTranscribeAudio` (`:195`). |
| `e2e/tests/cancel-recording.spec.ts` | New. Section 7. |
| `e2e/playwright.config.ts:11` | Add `cancel-recording` to `MIC_SPEC`. |
| `docs/superpowers/specs/2026-07-30-editable-voice-transcript-design.md` | Note in its non-goals that mid-recording cancel is now in scope; review-card discard still is not. |
| `AGENTS.md` | Project tree gains the two new files. Regenerated by `scripts/update_structure.py` in the lefthook pre-commit hook (`lefthook.yml:8-19`). |
