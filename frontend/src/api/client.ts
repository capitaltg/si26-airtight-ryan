// Typed fetch layer + TanStack Query hooks over the session/content API.
// Vite proxies `/api/*` to FastAPI and strips the `/api` prefix (vite.config.ts),
// so the browser calls `/api/sessions` and the backend sees `/sessions`.

import { useMutation, useQuery } from "@tanstack/react-query"

import type {
  AnswerResponse,
  ArchivedTranscript,
  ClarifyResponse,
  HistorySummary,
  PromptAudio,
  Report,
  RubricDisclosure,
  SessionState,
  Stage,
  TangentLimits,
  TranscribeResponse,
  VoiceAnswerResponse,
} from "../types"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // non-JSON error body — keep the status line
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// Submit an answer over SSE: the backend streams `{stage}` frames as the
// pipeline walks extracting → scoring → reacting, then one terminal `{result}`
// (the same AnswerResponse `/answer` returns) or an `{error}`. EventSource can't
// POST, so read the body stream by hand, splitting on the SSE frame delimiter.
async function submitAnswerStream(
  id: string,
  answer: string,
  onStage: (s: Stage) => void,
): Promise<AnswerResponse> {
  const res = await fetch(`/api/sessions/${id}/answer/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  })
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // non-JSON error body — keep the status line
    }
    throw new Error(detail)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let result: AnswerResponse | null = null

  for (;;) {
    const { done, value } = await reader.read()
    if (value) buffer += decoder.decode(value, { stream: true })
    // Frames are delimited by a blank line; process every complete one so far.
    let sep: number
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const line = frame.split("\n").find((l) => l.startsWith("data: "))
      if (!line) continue
      const ev = JSON.parse(line.slice(6)) as {
        stage?: Stage
        result?: AnswerResponse
        error?: string
      }
      if (ev.error) throw new Error(ev.error)
      if (ev.stage) onStage(ev.stage)
      if (ev.result) result = ev.result
    }
    if (done) break
  }

  if (!result) throw new Error("stream ended without a result")
  return result
}

// `signal` is optional and only voice transcription passes one: a mid-flight
// transcribe can be abandoned (nothing is written server-side either way),
// while a submitted answer cannot.
async function postMultipart<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "POST", body: form, signal })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // non-JSON error body — keep the status line
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// Voice mode's answer submission: a multipart recording, not JSON, so it can't
// go through `request` (which hardcodes a JSON Content-Type and would break the
// multipart boundary the browser needs to set itself).
async function submitAnswerAudio(
  id: string,
  blob: Blob,
  edit?: { answer: string; rawTranscript: string },
): Promise<VoiceAnswerResponse> {
  const form = new FormData()
  form.append("audio", blob, "answer.webm")
  if (edit) {
    form.append("answer", edit.answer)
    form.append("raw_transcript", edit.rawTranscript)
  }
  return postMultipart<VoiceAnswerResponse>(`/sessions/${id}/answer_audio`, form)
}

async function transcribeAudio(
  id: string,
  blob: Blob,
  signal?: AbortSignal,
): Promise<TranscribeResponse> {
  const form = new FormData()
  form.append("audio", blob, "answer.webm")
  return postMultipart<TranscribeResponse>(`/sessions/${id}/transcribe_audio`, form, signal)
}

export const api = {
  createSession: () => request<SessionState>("/sessions", { method: "POST" }),
  getSession: (id: string) => request<SessionState>(`/sessions/${id}`),
  submitAnswer: (id: string, answer: string) =>
    request<AnswerResponse>(`/sessions/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  submitAnswerStream,
  submitAnswerAudio,
  transcribeAudio,
  promptAudio: (id: string) => request<PromptAudio>(`/sessions/${id}/prompt_audio`),
  askClarification: (id: string, question: string) =>
    request<ClarifyResponse>(`/sessions/${id}/clarify`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  getRubric: () => request<RubricDisclosure>("/content/rubric"),
  getTangentLimits: () => request<TangentLimits>("/content/tangent-limits"),
  getReport: (id: string) => request<Report>(`/sessions/${id}/report`),
  getHistory: () => request<HistorySummary[]>("/sessions/history"),
  getTranscript: (id: string) => request<ArchivedTranscript>(`/sessions/${id}/transcript`),
}

// Create-a-session mutation: the rehearsal starts empty and the presenter clicks
// "Start rehearsal", so a mutation (not a query) models the one-shot POST.
export function useCreateSession() {
  return useMutation({ mutationFn: api.createSession })
}

// The mutation streams stage progress: callers pass the answer plus an `onStage`
// callback that fires as each pipeline stage begins, and the mutation resolves
// with the same AnswerResponse the JSON endpoint returns.
export function useSubmitAnswer(sessionId: string | null) {
  return useMutation({
    mutationFn: ({ answer, onStage }: { answer: string; onStage: (s: Stage) => void }) => {
      if (!sessionId) throw new Error("no active session")
      return api.submitAnswerStream(sessionId, answer, onStage)
    },
  })
}

// Voice mode's answer mutation: uploads the recorded blob and resolves with the
// transcript, score, and spoken reply/next-prompt audio all in one round trip.
export function useSubmitAnswerAudio(sessionId: string | null) {
  return useMutation({
    mutationFn: ({
      blob,
      answer,
      rawTranscript,
    }: {
      blob: Blob
      answer: string
      rawTranscript: string
    }) => {
      if (!sessionId) throw new Error("no active session")
      return api.submitAnswerAudio(sessionId, blob, { answer, rawTranscript })
    },
  })
}

export function useTranscribeAudio(sessionId: string | null) {
  return useMutation({
    mutationFn: ({ blob, signal }: { blob: Blob; signal?: AbortSignal }) => {
      if (!sessionId) throw new Error("no active session")
      return api.transcribeAudio(sessionId, blob, signal)
    },
  })
}

// Speak the active prompt. A mutation rather than a query: it fires from the
// voice-toggle click, and every switch into voice should get a fresh clip
// rather than a cached response.
export function useSpeakPrompt(sessionId: string | null) {
  return useMutation({
    mutationFn: () => {
      if (!sessionId) throw new Error("no active session")
      return api.promptAudio(sessionId)
    },
  })
}

// Ask a clarifying question. Plain POST (no SSE): the backend makes one quick
// react call and returns the reply plus the unchanged active prompt.
export function useAskClarification(sessionId: string | null) {
  return useMutation({
    mutationFn: (question: string) => {
      if (!sessionId) throw new Error("no active session")
      return api.askClarification(sessionId, question)
    },
  })
}

// The disclosed rubric is authored content loaded at startup — it never changes
// within a session, so cache it indefinitely.
export function useRubric() {
  return useQuery({
    queryKey: ["rubric"],
    queryFn: api.getRubric,
    staleTime: Infinity,
  })
}

export function useTangentLimits() {
  return useQuery({
    queryKey: ["tangent-limits"],
    queryFn: api.getTangentLimits,
    staleTime: Infinity,
  })
}

// The after-action report. Enabled only once the session is done, so the query
// fires when the presenter finishes. The scored part is deterministic; the one
// model narrative is regenerated per fetch, so don't over-cache it.
export function useReport(sessionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["report", sessionId],
    queryFn: () => {
      if (!sessionId) throw new Error("no active session")
      return api.getReport(sessionId)
    },
    enabled: enabled && sessionId !== null,
    staleTime: Infinity,
  })
}

// The past-rehearsals list. Refetched on mount rather than cached indefinitely:
// finishing a session changes it, and the rehearsal screen invalidates this key
// when a turn comes back done.
export function useHistory() {
  return useQuery({ queryKey: ["history"], queryFn: api.getHistory })
}

// One archived session's transcript. Archived rows never change, so cache it for
// the tab's life.
export function useArchivedTranscript(sessionId: string | null) {
  return useQuery({
    queryKey: ["transcript", sessionId],
    queryFn: () => {
      if (!sessionId) throw new Error("no session selected")
      return api.getTranscript(sessionId)
    },
    enabled: sessionId !== null,
    staleTime: Infinity,
  })
}
