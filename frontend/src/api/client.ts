// Typed fetch layer + TanStack Query hooks over the session/content API.
// Vite proxies `/api/*` to FastAPI and strips the `/api` prefix (vite.config.ts),
// so the browser calls `/api/sessions` and the backend sees `/sessions`.

import { useMutation, useQuery } from "@tanstack/react-query"

import type { AnswerResponse, Report, RubricDisclosure, SessionState } from "../types"

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

export const api = {
  createSession: () => request<SessionState>("/sessions", { method: "POST" }),
  getSession: (id: string) => request<SessionState>(`/sessions/${id}`),
  submitAnswer: (id: string, answer: string) =>
    request<AnswerResponse>(`/sessions/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),
  getRubric: () => request<RubricDisclosure>("/content/rubric"),
  getReport: (id: string) => request<Report>(`/sessions/${id}/report`),
}

// Create-a-session mutation: the rehearsal starts empty and the presenter clicks
// "Start rehearsal", so a mutation (not a query) models the one-shot POST.
export function useCreateSession() {
  return useMutation({ mutationFn: api.createSession })
}

export function useSubmitAnswer(sessionId: string | null) {
  return useMutation({
    mutationFn: (answer: string) => {
      if (!sessionId) throw new Error("no active session")
      return api.submitAnswer(sessionId, answer)
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
