// Voice-mode primitives: recording the presenter's spoken answer and playing
// back the persona's spoken reply. Kept separate from the components so the
// MediaRecorder/Audio-element plumbing doesn't clutter Rehearsal.tsx's state
// machine.

import { useEffect, useRef, useState } from "react"

// Preferred recording formats in order — the backend's transcriber/ffmpeg step
// (tasks 1-5) accepts any of these, so pick the first the browser actually
// supports rather than hardcoding one.
const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]

function pickMimeType(): string | undefined {
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t))
}

// Opens a capture stream on a specific input, or the system default when
// `deviceId` is null. `exact` rather than `ideal` so a stored id that no longer
// resolves fails loudly instead of silently recording from a different
// microphone — a wrong-device capture produces a bad answer with a real score
// attached, which is worse than an error. Over-constrained is retried once
// against the default; Chrome reports that as either OverconstrainedError or
// NotFoundError depending on version, so both names retry.
const FALLBACK_ERRORS = new Set(["OverconstrainedError", "NotFoundError"])

export async function openAudioStream(deviceId?: string | null): Promise<MediaStream> {
  const constraints: MediaStreamConstraints = {
    audio: deviceId ? { deviceId: { exact: deviceId } } : true,
  }
  try {
    return await navigator.mediaDevices.getUserMedia(constraints)
  } catch (err) {
    const name = (err as { name?: string } | null)?.name
    if (deviceId && name && FALLBACK_ERRORS.has(name)) {
      return await navigator.mediaDevices.getUserMedia({ audio: true })
    }
    throw err
  }
}

// Records one hold-to-talk answer. `start`/`stop` bracket a single recording;
// calling `start` again after `stop` begins a fresh one. Permission denial (or
// any other getUserMedia failure) surfaces through `error`, not a rejected
// promise the caller must try/catch — this mirrors how the rest of this
// codebase's hooks expose failures as state (see `useSubmitAnswer` /
// `useCreateSession` in api/client.ts) rather than thrown exceptions.
// `deviceId` selects the input to record from; null/undefined records from the
// system default, so existing call sites keep working untouched.
export function useRecorder(deviceId?: string | null): {
  recording: boolean
  start: () => Promise<void>
  stop: () => Promise<Blob>
  error: string | null
} {
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  function releaseStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }

  // Release the mic on unmount too, so navigating away mid-recording doesn't
  // leave the browser's mic-in-use indicator on.
  useEffect(() => releaseStream, [])

  async function start() {
    setError(null)
    try {
      const stream = await openAudioStream(deviceId)
      streamRef.current = stream
      const mimeType = pickMimeType()
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorderRef.current = recorder
      recorder.start()
      setRecording(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access was denied.")
      releaseStream()
    }
  }

  function stop(): Promise<Blob> {
    return new Promise((resolve) => {
      const recorder = recorderRef.current
      if (!recorder || recorder.state === "inactive") {
        resolve(new Blob(chunksRef.current))
        return
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType })
        chunksRef.current = []
        recorderRef.current = null
        releaseStream()
        setRecording(false)
        resolve(blob)
      }
      recorder.stop()
    })
  }

  return { recording, start, stop, error }
}

// A single reusable `Audio` element, shared between `primePlayback` (called
// synchronously inside the hold-to-talk pointer gesture) and `playSequence`
// (called later, well outside any user gesture, once the record → upload →
// score → synthesize round trip resolves). Browsers key "has a real user
// gesture unlocked autoplay here" to the specific element/context that was
// played during the gesture, not to autoplay having been used anywhere —
// so priming a *different* `Audio` instance (or one with no `src`) than the
// one `playSequence` later plays does nothing for Safari's autoplay policy.
const playbackEl = new Audio()

// Bumped every time `primePlayback` or `playSequence` (re)claims `playbackEl`
// for its own use. `playSequence` captures the value at call time and each
// iteration checks it's still current before advancing to the next clip — if
// something else has since reassigned `playbackEl.src` (another priming call,
// or an overlapping `playSequence`), the current chain's `ended`/`error`
// listeners can still fire on whatever now plays on the shared element (a
// reassigned `.src` aborts playback without ever firing `ended`/`error` on the
// abandoned clip), so without this check a stale iteration would wrongly
// advance and play its next queued clip unmuted over whatever claimed the
// element after it.
let playbackGeneration = 0

// The shortest valid silent audio clip: a 1-sample, 8kHz mono WAV. Used only
// to give the shared element a real `src` to play during the priming call —
// its content is irrelevant, only that `.play()` runs inside the gesture.
const SILENT_CLIP_DATA_URL =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="

// Call synchronously from inside a real user-gesture handler (e.g.
// `pointerdown`) to unlock `playbackEl` for the browser's autoplay policy
// before `playSequence` reuses it later, outside any gesture, to play the
// persona's spoken reply.
export function primePlayback(): void {
  playbackGeneration += 1
  playbackEl.muted = true
  playbackEl.src = SILENT_CLIP_DATA_URL
  playbackEl
    .play()
    .catch(() => {
      // Priming is best-effort; a rejected muted play() just means the later
      // reply falls back to the manual <audio controls> in the transcript.
    })
    .finally(() => {
      playbackEl.muted = false
    })
}

// Plays a list of base64-encoded mp3 clips back to back, waiting for each
// clip's `ended` event before starting the next. Callers (Rehearsal.tsx) pass
// raw base64 straight from the API response (`reply_audio`/`next_prompt_audio`
// on VoiceAnswerResponse), so the data-URL wrapping happens here, once. A
// clip that fails to play (e.g. the browser blocking autoplay outside a user
// gesture) is skipped rather than rejecting the whole sequence — the caller
// falls back to a manual `<audio controls>` in the transcript for that case.
// Reuses `playbackEl` (rather than constructing a new `Audio` per clip) so
// the gesture-unlocked state from `primePlayback` actually carries over.
export function playSequence(sources: string[]): Promise<void> {
  // Claim the element for this call. An overlapping `playSequence` call (or a
  // `primePlayback` in between clips) bumps this again, which the check below
  // uses to detect that this chain's turn is over.
  const generation = ++playbackGeneration
  return sources.reduce<Promise<void>>(
    (chain, source) =>
      chain.then(
        () =>
          new Promise<void>((resolve) => {
            // Something else has since claimed `playbackEl` (superseded this
            // call entirely) — bail without touching `.src` so we don't step
            // on whatever's now playing.
            if (generation !== playbackGeneration) {
              resolve()
              return
            }
            const onEnded = () => {
              cleanup()
              resolve()
            }
            const onError = () => {
              cleanup()
              resolve()
            }
            function cleanup() {
              playbackEl.removeEventListener("ended", onEnded)
              playbackEl.removeEventListener("error", onError)
            }
            playbackEl.addEventListener("ended", onEnded, { once: true })
            playbackEl.addEventListener("error", onError, { once: true })
            playbackEl.src = `data:audio/mp3;base64,${source}`
            playbackEl.play().catch(() => {
              cleanup()
              resolve()
            })
          }),
      ),
    Promise.resolve(),
  )
}

// `setSinkId` is Chromium-only and is not in TypeScript 5.6's DOM lib, so the
// element is narrowed through this optional-method type rather than `any`.
type SinkCapableMedia = HTMLMediaElement & { setSinkId?: (deviceId: string) => Promise<void> }

// Routes everything that plays on the shared element — persona replies, spoken
// prompts, the test tone — to `deviceId`. An empty string means "system
// default". A rejected setSinkId resolves rather than throws: an unroutable
// output should not break the caller's effect, and the reply still plays on
// whatever the browser falls back to.
export async function setOutputDevice(deviceId: string | null): Promise<void> {
  const el = playbackEl as SinkCapableMedia
  if (typeof el.setSinkId !== "function") return
  try {
    await el.setSinkId(deviceId ?? "")
  } catch {
    // Deliberately swallowed — see above.
  }
}

// Whether an output picker is a real control or dead UI on this browser.
export function outputSelectionSupported(): boolean {
  return "setSinkId" in HTMLMediaElement.prototype
}

const TONE_HZ = 440
const TONE_SAMPLE_RATE = 8000
const TONE_SECONDS = 0.6
// Samples to ramp in and out over, so the tone does not start or end on a click.
const TONE_FADE_SAMPLES = 40

// An 8-bit unsigned mono PCM WAV built in JS: the same header shape as
// SILENT_CLIP_DATA_URL above, with real sample data. Generated rather than
// shipped as an asset so the bundle stays free of binary audio. Built once and
// cached — the bytes never change.
let toneUrl: string | null = null

function toneDataUrl(): string {
  if (toneUrl) return toneUrl
  const sampleCount = Math.floor(TONE_SAMPLE_RATE * TONE_SECONDS)
  const bytes = new Uint8Array(44 + sampleCount)
  const view = new DataView(bytes.buffer)
  function ascii(offset: number, text: string) {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  ascii(0, "RIFF")
  view.setUint32(4, 36 + sampleCount, true)
  ascii(8, "WAVEfmt ")
  view.setUint32(16, 16, true) // fmt chunk size
  view.setUint16(20, 1, true) // format: PCM
  view.setUint16(22, 1, true) // channels: mono
  view.setUint32(24, TONE_SAMPLE_RATE, true)
  view.setUint32(28, TONE_SAMPLE_RATE, true) // byte rate: 1 byte per sample, mono
  view.setUint16(32, 1, true) // block align
  view.setUint16(34, 8, true) // bits per sample
  ascii(36, "data")
  view.setUint32(40, sampleCount, true)
  for (let i = 0; i < sampleCount; i += 1) {
    const fade = Math.min(1, i / TONE_FADE_SAMPLES, (sampleCount - i) / TONE_FADE_SAMPLES)
    const sample = Math.sin((2 * Math.PI * TONE_HZ * i) / TONE_SAMPLE_RATE) * fade
    view.setUint8(44 + i, Math.round(128 + sample * 100))
  }
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  toneUrl = `data:audio/wav;base64,${btoa(binary)}`
  return toneUrl
}

// Plays a short tone through the shared element so the presenter can confirm
// the selected output actually reaches their ears. Claims `playbackEl` under
// the same `playbackGeneration` protocol `playSequence` uses, so a tone and an
// in-flight reply sequence cannot fight over the element: bumping the counter
// tells any live sequence its turn is over. Resolves (never rejects) when the
// clip ends, errors, or is blocked, matching `playSequence`.
export function playTestTone(): Promise<void> {
  playbackGeneration += 1
  return new Promise<void>((resolve) => {
    function settle() {
      playbackEl.removeEventListener("ended", settle)
      playbackEl.removeEventListener("error", settle)
      resolve()
    }
    playbackEl.addEventListener("ended", settle, { once: true })
    playbackEl.addEventListener("error", settle, { once: true })
    playbackEl.muted = false
    playbackEl.src = toneDataUrl()
    playbackEl.play().catch(settle)
  })
}
