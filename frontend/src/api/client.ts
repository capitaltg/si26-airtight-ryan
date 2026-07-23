// Typed fetch layer + TanStack Query hooks over the session/content API.
// Vite proxies `/api/*` to FastAPI and strips the `/api` prefix (vite.config.ts),
// so the browser calls `/api/sessions` and the backend sees `/sessions`.

import { useMutation, useQuery } from "@tanstack/react-query"

import type {
  AnswerResponse,
  ClarifyResponse,
  Report,
  RubricDisclosure,
  SessionState,
  Stage,
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

export const api = {
  createSession: () => request<SessionState>("/sessions", { method: "POST" }),
  getSession: (id: string) => request<SessionState>(`/sessions/${id}`),
  submitAnswer: (id: string, answer: string) =>
    request<AnswerResponse>(`/sessions/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  submitAnswerStream,
  askClarification: (id: string, question: string) =>
    request<ClarifyResponse>(`/sessions/${id}/clarify`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  getRubric: () => request<RubricDisclosure>("/content/rubric"),
  getReport: (id: string) => request<Report>(`/sessions/${id}/report`),
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
