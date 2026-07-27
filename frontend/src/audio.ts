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

// Records one hold-to-talk answer. `start`/`stop` bracket a single recording;
// calling `start` again after `stop` begins a fresh one. Permission denial (or
// any other getUserMedia failure) surfaces through `error`, not a rejected
// promise the caller must try/catch — this mirrors how the rest of this
// codebase's hooks expose failures as state (see `useSubmitAnswer` /
// `useCreateSession` in api/client.ts) rather than thrown exceptions.
export function useRecorder(): {
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
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
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

// Plays a list of base64-encoded mp3 clips back to back, waiting for each
// clip's `ended` event before starting the next. Callers (Rehearsal.tsx) pass
// raw base64 straight from the API response (`reply_audio`/`next_prompt_audio`
// on VoiceAnswerResponse), so the data-URL wrapping happens here, once. A
// clip that fails to play (e.g. the browser blocking autoplay outside a user
// gesture) is skipped rather than rejecting the whole sequence — the caller
// falls back to a manual `<audio controls>` in the transcript for that case.
export function playSequence(sources: string[]): Promise<void> {
  return sources.reduce<Promise<void>>(
    (chain, source) =>
      chain.then(
        () =>
          new Promise<void>((resolve) => {
            const audio = new Audio(`data:audio/mp3;base64,${source}`)
            audio.addEventListener("ended", () => resolve(), { once: true })
            audio.addEventListener("error", () => resolve(), { once: true })
            audio.play().catch(() => resolve())
          }),
      ),
    Promise.resolve(),
  )
}
