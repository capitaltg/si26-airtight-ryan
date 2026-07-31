# Editable voice transcript — design

Date: 2026-07-30
Status: proposed

## 1. Context

AWS Transcribe output is inconsistent. Today a voice answer goes from mic to score in one round trip: `stopRecording` (`frontend/src/components/Rehearsal.tsx:413`) → `POST /sessions/{id}/answer_audio` (`server/app/api/sessions.py:449`) → transcribe → `orchestrator.submit_answer` → extraction / scoring / reaction.

The presenter never sees what the model heard until the turn is already scored and the meter has moved (`frontend/src/components/ChatTurn.tsx:51-65`, label "What the scorer heard"). A misheard number or a dropped "not" costs a real turn, and turns are append-only — there is no recovery.

This design splits the voice turn into **transcribe, then score**, with an editable review step between them. Nothing touches the DB or the LLM until the presenter confirms.

**Scope: this is a transcription-correction step, not a retake.** The delivery becomes locked when transcription reaches the review card. Cancellation is available only before a transcript and review card exist. Once the card is on screen, it exists so a misheard number or a dropped "not" can be fixed before scoring; it is not a preview screen for deciding whether the answer was good enough.

## 2. Decisions

| Question | Decision | Why |
|---|---|---|
| Where the edit sits | Always review before scoring. A transcribe-only endpoint, then submit. | No opt-in toggle (two code paths to maintain) and no post-hoc turn mutation (turns are append-only and the report snapshot must match the transcript). |
| Exits from the review card | **Submit only.** No re-record, no discard. | Either one is a retake under another name: dump a bad delivery, hold the button again, no turn consumed. Once transcription reaches the review card, the delivery is locked; cancellation is available only before then. |
| Tangent limit on an edited turn | Stays `voice_seconds`, measured on recorded audio duration. | Editing fixes transcription; it is not a way to trim a 90-second ramble into 40 words and dodge the voice penalty. |
| Audit trail | Store both: `turns.transcript` = raw model output, `turns.user_answer` = edited text that was scored. | Both columns already exist. Gives "you corrected this" in the UI and real data on transcription quality. |
| Audio between steps | Re-upload the blob on step 2. | Stateless. 60s of opus is ~200 KB, and there is no pending-upload store to expire or clean up. |

## 3. Flow

```
hold to talk / release
  POST /sessions/{id}/transcribe_audio        (multipart: audio)
    -> { transcript, duration_seconds }        no DB write, no LLM call

┌ Fix what we heard ─────────────────┐
│ so the the margin was uh twenty…   │  editable textarea
└────────────────────────────────────┘
  1:12 recorded / 1:00 limit                       [Submit]

  POST /sessions/{id}/answer_audio            (multipart: audio + answer + raw_transcript)
    -> scores the edited text, persists the raw transcript alongside it
```

## 4. Backend

### 4.1 New: `POST /sessions/{session_id}/transcribe_audio`

Declared in `server/app/api/sessions.py` next to `submit_answer_audio` (~L449). Reuses, unchanged:

- `_require_live_session` (L359) — archived session still 409s.
- The empty-upload and `settings.max_answer_audio_bytes` checks (L470-474) — 422 / 413.
- `_safe_audio_content_type` (L69) — the replay-header allowlist.
- The `get_transcriber` dependency (`server/app/api/deps.py:63`) and the `isinstance(transcription, str)` compat shim (L486).

Response model:

```python
class TranscribeResponse(BaseModel):
    transcript: str
    duration_seconds: float
```

Two deliberate differences from `answer_audio`:

- **A blank transcript returns 200 with `transcript: ""`**, not 422. The review card is the recovery path — the presenter types the answer or re-records. The current 422 (`sessions.py:488`) exists only because there was nowhere to put an empty result.
- No DB write and no Bedrock call at all, so a failed or blank transcription cannot cost a turn.

`TranscriptionError` → 422 `"Could not transcribe the recording"` (same wording as today).

### 4.2 Extended: `POST /sessions/{session_id}/answer_audio`

Two new optional form fields:

```python
answer: str | None = Form(None)          # the confirmed/edited text to score
raw_transcript: str | None = Form(None)  # what step 1 heard, for the audit trail
```

Branching:

- **`answer` blank or absent** — today's behavior, verbatim. Transcribe, score the transcript. Every existing test and the `docs/prs/voice-chat-rehearsal-mode.md` contract stay green.
- **`answer` present** — **no transcription call at all.** Duration is measured server-side from the re-uploaded bytes; the client never supplies a duration, so the `voice_seconds` limit cannot be gamed by editing. Then:

```python
orchestrator.submit_answer(
    db, content, client, session, answer,
    audio=AnswerAudio(
        data=data,
        content_type=content_type,
        transcript=raw_transcript or answer,
        duration_seconds=measured,
    ),
)
```

`raw_transcript` is client-supplied and therefore untrusted, but it is audit metadata only — it is never scored, never shown to the model, and never used for the limit. Worst case a presenter fakes their own audit trail.

### 4.3 New duration helper and DI seam

- `measure_duration(audio: bytes, content_type: str) -> float` in `server/app/voice/transcribe.py` — `to_pcm16` (`server/app/voice/audio.py:21`) then the existing `duration_seconds` (`transcribe.py:36`). It lives in `transcribe.py` because that module already imports both; putting it in `audio.py` would be a circular import.
- `DurationMeasurer` Protocol + `get_duration_measurer()` in `server/app/api/deps.py`, mirroring `Transcriber` (L55-63). This is the override seam so pytest never shells out to ffmpeg.

Cost: one extra ffmpeg decode on the edited path (it replaces the transcription call, which was far more expensive). Rejected alternative: return an HMAC-signed duration token from step 1 — more moving parts for the same guarantee.

### 4.4 Untouched

`orchestrator.submit_answer_events` already treats `answer` as opaque text and `audio.duration_seconds` as the only voice signal reaching scoring (`server/app/pipeline/orchestrator.py:300-314`). `AnswerAudio.transcript` already means "what the recording transcribed to" and is forwarded straight to `repo.append_turn` (L359). Scoring, the rubric, config thresholds, and the `LimitMeasurement` schema all stay as they are.

### 4.5 Persistence — no migration

| Column | Meaning after this change |
|---|---|
| `turns.user_answer` (`server/app/db/models.py:98`) | the text that was scored — edited if the presenter edited it |
| `turns.transcript` (L110) | the raw model transcript, voice turns only |

"Was it edited" is derived: `transcript != user_answer`. No new column, no flag to keep in sync.

Audio is still purged at archive time (`server/app/session_archive.py:87`); `transcript` survives, so history keeps both texts. `ArchivedTurnDTO.transcript` (`sessions.py:167`) already carries the raw value.

## 5. Frontend

### 5.1 New component: `frontend/src/components/VoiceReview.tsx`

Presentational, no data fetching. `Rehearsal.tsx` is already 927 lines and owns all session state; the review card gets its own file rather than a fifth branch inside it.

Props: `rawTranscript`, `text`, `onChange`, `durationSeconds`, `limits` (`TangentLimits["voice"]`), `submitting`, `error`, `onSubmit`.

- Heading and helper copy name the job: "Fix what we heard" / "Correct anything the transcriber got wrong. Your recording is already locked in."
- The textarea reuses the class string from `Rehearsal.tsx:768-778` — the de-facto input style, since there is no design system (`AGENTS.md:268`).
- The duration readout reuses the three-state slate → amber → red pattern from `Rehearsal.tsx:839-858`, measured in **recorded seconds**, not words. The limit is still `voice_seconds`. It is a readout, not a warning to act on — the recording is already fixed, so the amber/red state is telling the presenter what this turn will cost, not offering a chance to redo it.
- Submit is the only action. Disabled on `!text.trim()` and while `submitting`.
- `data-testid` on the card, the textarea, and the duration readout. (The existing limit counters have none, which is why `e2e/tests/tangent-limits.spec.ts` matches on text content.)

### 5.2 `Rehearsal.tsx`

New state:

```ts
const [review, setReview] = useState<{
  asked: PromptDTO
  blob: Blob
  rawTranscript: string
  text: string
  durationSeconds: number
} | null>(null)
```

`asked` is captured at record time, for the same reason `stopRecording` captures `const asked = prompt` today (L416).

- `stopRecording` (L413) calls `transcribeAudio.mutate(blob)` instead of `submitAudio.mutate(blob)`. No optimistic `pending` turn and no `setStage` here anymore — nothing is being scored yet. On success it sets `review`. All the existing ref guards (`recordingActiveRef`, `startPromiseRef`, `stopInFlightRef`) and the `blob.size === 0` early return stay exactly as they are.
- New `submitReview()` runs what `stopRecording` used to own (L432-472): `setPending({ prompt: asked, answer: review.text })` — now with real text instead of the blank placeholder the comment at L428-430 apologizes for — `setStage("extracting")`, `submitAudio.mutate({ blob, answer, rawTranscript })`, then the existing transcript-append / meters / `playSequence` block unchanged. `setReview(null)` on success only, so a failed submit keeps the edited text.
- Push-to-talk gate becomes `pushToTalkEnabled && review === null` (L504). Space pressed outside the textarea must not start a second recording while one is pending review — there is nowhere for the first blob to go. (Space *inside* the textarea is already safe via `isTypingTarget`, L510-519.)
- The Text/Voice toggle (L737-760) is disabled while `review !== null`. Switching to text mode would abandon the recorded blob and let the presenter type a fresh answer — the retake this design rules out. Same reason the Mic check button (L726-733) is disabled: it tears down the stream mid-turn.
- `primePlayback()` must now also run inside the Submit click — the persona's reply clip plays after the step-2 round trip, well outside the record gesture. `beginRecording` (L352) keeps its own call for the prompt read-aloud path.
- Object-URL lifecycle unchanged: the blob only becomes an object URL on submit success (existing L452), and a review can only end in submit. Existing cleanup at L144-154 and L192-194 is unchanged.

### 5.3 API client and types

- `frontend/src/api/client.ts`: `api.transcribeAudio(id, blob)` + `useTranscribeAudio`, alongside `submitAnswerAudio` (L98-113) and using the same multipart `FormData` shape that bypasses the JSON `request()` helper. `submitAnswerAudio` takes an optional `{ answer, rawTranscript }` and appends the fields when present.
- `frontend/src/types.ts`: add `TranscribeResponse`. `VoiceAnswerResponse.transcript` (L77-81) is unchanged and now means "the text that was scored" — it echoes `answer` on the edited path, so `ChatTurn` needs no new field.

### 5.4 `ChatTurn.tsx`

The "What the scorer heard" label (L51-65) is now wrong for an edited turn — the scorer heard `answer`. Render `answer` plus `<audio controls>`, and when `transcript !== answer`, a collapsed `<details>` "Original transcription" holding the raw text. Follows the existing disclosure pattern in `AfterActionReport.tsx:52-69`. `ArchiveView.tsx` passes both fields through unchanged.

## 6. Errors and edge cases

| Case | Behavior |
|---|---|
| Step 1 transcription fails | Red error under the talk button (the `submitAudio.isError` pattern, `Rehearsal.tsx:886`). No review card, no turn consumed, nothing persisted — the recording is lost and the presenter answers again. This is the one path that ends without a scored turn, and it is a server failure, not a presenter choice. |
| Blank transcript | Review card opens empty: "Nothing was heard. Type what you said." The card is the recovery path; there is no re-record button behind it. |
| Presenter blanks the textarea | Submit disabled. The card cannot be dismissed, so the turn cannot be abandoned by emptying it. |
| Session completed or archived between steps | Step 2 409s via `_require_live_session`. Surface the error; the card stays so the text is visible, but the session is over and the turn is gone either way. |
| Step 2 fails | `setPending(null)`, review card stays populated, retry is one click. Submit is the only button, so retry is the only affordance. |
| Empty blob (getUserMedia failed mid-press) | Existing `blob.size === 0` early return (L427) — no request, no card. |
| Presenter reloads the page mid-review | The blob is in memory only; the turn was never created. On reload the prompt is unanswered and they answer again. Accepted: closing the tab to escape a bad answer is not a hole worth a pending-upload store. |
| Oversize / disallowed content type | Same 413 and allowlist handling on both endpoints. |

## 7. Test plan

**pytest — `server/tests/test_api_voice.py`** (extends the existing 25 cases):

- `transcribe_audio` returns transcript + duration, creates **no** turn row, and moves no meter.
- Blank transcript → 200 with `transcript == ""`.
- Oversize → 413; archived session → 409; empty upload → 422.
- `answer_audio` with `answer` set scores the **edited** text (assert via the fake Bedrock client's captured extraction prompt) and never calls the transcriber.
- Persistence: `user_answer == edited`, `transcript == raw_transcript`.
- The limit is `voice_seconds` with the server-measured duration; there is no client field that could override it.
- `test_answer_audio_scores_identically_to_text_answer` (L74) must still pass **unmodified** — it is the guard that the no-`answer` path is untouched.

**pytest — `server/tests/test_voice_transcribe.py`:** `measure_duration` derives seconds from decoded PCM frames (mirrors the existing case at L133-137).

**Playwright — new `e2e/tests/voice-transcript-edit.spec.ts`:** needs a real recording, so it joins the `mic` project matcher in `e2e/playwright.config.ts:28-38` (fake media device, granted permission). Route-stub `transcribe_audio` with a deliberately wrong transcript and `answer_audio` with a fixed result. Assert: the review card renders the wrong text; editing and submitting produces a transcript bubble with the edited text; the "Original transcription" disclosure holds the raw text; the captured `answer_audio` request body carried the edited `answer`.

Plus the no-retake guards, since they are the part a future refactor will quietly break: with the review card open, the Text/Voice toggle is disabled, and pressing Space outside the textarea starts no second recording (assert `transcribe_audio` was called exactly once).

**Manual:** run the stack, record a deliberately garbled answer, confirm the review card, edit, submit, then confirm the report and `GET /sessions/{id}/transcript` show the edited text scored with the raw transcript retained.

## 8. Non-goals

- SSE stage stepper for voice — the known asymmetry where stage sticks at "extracting" (`Rehearsal.tsx:431`). Separate change.
- Re-recording or discarding an answer **from the review card**. The presenter
  gets one delivery per prompt; this change only lets them correct what the
  transcriber misheard. Cancelling a take *before* a transcript exists is now in
  scope: see `2026-07-30-cancel-microphone-input-design.md`. Once a transcript is
  on screen, the exits are still Submit only.
- Editing or re-scoring a turn after submission.
- Live / partial transcripts while recording (`server/app/voice/transcribe.py:55` deliberately drops partials).
- Voice clarifications — still text-only (`Rehearsal.tsx:835-837`).
- Any change to thresholds, the rubric, or the penalty value.

## 9. Files

| File | Change |
|---|---|
| `server/app/api/sessions.py` | new `transcribe_audio` route; `answer_audio` gains `answer` / `raw_transcript` form fields |
| `server/app/api/deps.py` | `DurationMeasurer` protocol + `get_duration_measurer` |
| `server/app/voice/transcribe.py` | `measure_duration` |
| `frontend/src/components/VoiceReview.tsx` | new |
| `frontend/src/components/Rehearsal.tsx` | two-step voice flow, `review` state, push-to-talk gate, mode toggle disabled during review |
| `frontend/src/components/ChatTurn.tsx` | raw-vs-scored rendering |
| `frontend/src/api/client.ts`, `frontend/src/types.ts` | transcribe hook + types |
| `e2e/tests/voice-transcript-edit.spec.ts`, `e2e/playwright.config.ts` | new spec in the `mic` project |
| `server/tests/test_api_voice.py`, `server/tests/test_voice_transcribe.py` | cases in §7 |
| `AGENTS.md` | `STRUCTURE:START`/`END` tree — required in the same change as any file add (`AGENTS.md:262`) |

No Alembic migration. No config or rubric change.
