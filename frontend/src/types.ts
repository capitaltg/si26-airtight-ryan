// TypeScript mirrors of the FastAPI DTOs (server/app/api/sessions.py, content.py).
// Kept hand-written and narrow: the rehearsal UI (task 11) consumes the session
// and content contracts only. The full Extraction / report shapes belong to the
// after-action report (task 12) and are intentionally omitted here.

export interface Meter {
  persona_id: string
  support: number
  capped: boolean
}

export interface Prompt {
  persona_id: string
  display_name: string
  concern_id: string
  prompt: string
  is_follow_up: boolean
  // The persona's self-introduction, non-null only on the first prompt they ask
  // in a session (their opening question, or the first question after a handoff).
  intro: string | null
}

// The active prompt spoken aloud (GET /sessions/{id}/prompt_audio): one base64
// mp3 of the persona's intro plus their question, null when synthesis failed.
export interface PromptAudio {
  audio: string | null
}

export interface SessionState {
  id: string
  status: string
  persona_ids: string[]
  meters: Meter[]
  concern_status: Record<string, string>
  prompt: Prompt | null // null once the session is complete
  done: boolean
}

// The scoring pipeline stage currently running, streamed from the SSE endpoint
// so the UI can show which step the wait is on rather than an opaque spinner.
export type Stage = "extracting" | "scoring" | "reacting"

export interface AnswerResponse {
  reply: string
  rationale: string
  persona_id: string
  concern_id: string
  concern_status: string
  support_delta: number
  raw_support_delta: number
  matched_rows: string[]
  row_counts: Record<string, number>
  meter: number
  capped: boolean
  limit: LimitResult | null
  meters: Meter[]
  next_prompt: Prompt | null
  done: boolean
}

export interface TangentLimits {
  text: { warning: number; limit: number; unit: "words" }
  voice: { warning: number; limit: number; unit: "seconds" }
  penalty: number
}

export interface LimitResult {
  kind: "text_words" | "voice_seconds"
  measured: number
  warning_threshold: number
  limit_threshold: number
  exceeded: boolean
  penalty_applied: boolean
  penalty_value: number
}

// Voice mode's answer response: everything AnswerResponse carries, plus what
// the presenter's recording produced.
export interface VoiceAnswerResponse extends AnswerResponse {
  transcript: string
  reply_audio: string | null
  next_prompt_audio: string | null
}

export interface TranscribeResponse {
  transcript: string
  duration_seconds: number
}

// A clarification is a non-scored turn: the evaluator answers a clarifying
// question, the meter does not move, and the same prompt stays active.
export interface ClarifyResponse {
  reply: string
  persona_id: string
  concern_id: string
  remaining: number // clarifications left on this concern
  prompt: Prompt // unchanged active prompt
}

// --- disclosed rubric panel (GET /content/rubric) ---

export interface RubricRow {
  id: string
  description: string
  support_value: number
  cap: number | null
  note: string | null
}

// A red line is the server's `{id, text}` shape for an authored finding —
// the same shape the persona editor's `NonNegotiable` (defined below) uses,
// so this reuses it rather than declaring an identical type under a new name.
export interface ConcernDisclosure {
  concern_id: string
  core_ask: string
  what_would_satisfy: string
  red_lines: NonNegotiable[]
}

export interface RubricDisclosure {
  version: number
  rows: RubricRow[]
  combination: string[]
  concerns: ConcernDisclosure[]
}

// --- after-action report (GET /sessions/{id}/report) ---
// Mirrors server/app/schemas/report.py. The scored part is code-rendered and
// deterministic; the narrative is the one labeled "Not scored" model recap.

export interface PersonaLine {
  persona_id: string
  support: number
  capped: boolean
}

export interface CoverageCounts {
  full: number
  partial: number
  none: number
}

export interface RateStats {
  total_turns: number
  dodge_count: number
  dodges_per_turn: number
  contradiction_count: number
  concerns_total: number
  concerns_satisfied: number
  coverage_rate: number
}

export interface FindingEvidence {
  span: string
  detail: string
}

export interface ScoredFinding {
  turn_index: number
  persona_id: string
  concern_id: string
  rubric_row: string
  support_value: number
  count: number
  evidence: FindingEvidence[]
}

export interface ClarificationLine {
  persona_id: string
  concern_id: string
  question: string
  reply: string
}

export interface NarrativeSection {
  scored: boolean
  header: string
  text: string
}

export interface Report {
  session_id: string
  status: string
  rate_stats: RateStats
  personas: PersonaLine[]
  coverage_counts: CoverageCounts
  dodge_counts_by_type: Record<string, number>
  contradiction_count: number
  findings: ScoredFinding[]
  limit_findings: LimitFinding[]
  clarifications: ClarificationLine[]
  narrative: NarrativeSection
}

export interface LimitFinding {
  turn_index: number
  persona_id: string
  concern_id: string
  kind: "text_words" | "voice_seconds"
  measured: number
  limit_threshold: number
  penalty: number
}

// A single completed exchange as accumulated client-side for the transcript.
// Built from the prompt shown plus the AnswerResponse it produced.
export interface TranscriptTurn {
  key: number // stable, append-only order key for React lists
  personaId: string
  displayName: string
  concernId: string
  isFollowUp: boolean
  prompt: string
  // The intro this turn was displayed with, so scrolling back shows where each
  // evaluator entered. Copied from the prompt at submit time — the backend never
  // persists it.
  intro?: string | null
  answer: string
  reply: string
  rationale: string
  supportDelta: number
  rawSupportDelta: number
  matchedRows: string[]
  rowCounts: Record<string, number>
  capped: boolean
  limit?: LimitResult | null
  // A clarification turn is not scored: ChatTurn branches on this to suppress the
  // delta badge and rubric chips. Absent/true means a normal scored turn.
  scored?: boolean
  // Voice mode only: the transcript the recording produced (the scorer's actual
  // input) and a playable URL for the presenter's own recorded answer. Absent
  // for text-mode turns, which render exactly as before.
  transcript?: string
  audioUrl?: string
}

// --- session history (GET /sessions/history, GET /sessions/{id}/transcript) ---

// One past rehearsal as summarized for the list. `archived_at` is when it became
// history and is the list's sort key.
export interface HistorySummary {
  id: string
  created_at: string
  archived_at: string
  status: string // "complete" | "ended"
  turn_count: number
  meters: Meter[]
  concerns_satisfied: number
  concerns_total: number
}

// One exchange from an archived session. Field names mirror TranscriptTurn above
// so ChatTurn renders it unchanged.
export interface ArchivedTurn {
  persona_id: string
  display_name: string
  concern_id: string
  is_follow_up: boolean
  prompt: string
  intro: string | null
  answer: string
  reply: string
  rationale: string
  support_delta: number
  raw_support_delta: number
  matched_rows: string[]
  row_counts: Record<string, number>
  capped: boolean
  scored: boolean
  transcript: string | null
  limit: LimitResult | null
}

export interface ArchivedTranscript {
  turns: ArchivedTurn[]
}

// --- persona editor (server/app/api/personas.py) ---

export interface PersonaExemplar {
  persona: string
  user: string
  support_delta: number
  note: string
}

// A non-negotiable's `id` is the server's join key for a scored red-line
// finding, so both this and `ConcernDisclosure.red_lines` above carry it
// through unedited — one `{id, text}` shape, not a duplicate per call site.
export interface NonNegotiable {
  id: string
  text: string
}

export interface NonNegotiableDraft {
  id?: string
  text: string
}

// Read shape: includes the fields the editor renders read-only.
export interface Persona {
  id: string
  display_name: string
  intro: string
  voice: string
  demographics: string
  values: string[]
  wants: string[]
  priorities: string[]
  non_negotiables: NonNegotiable[]
  rubric_version: number
  polly_voice_id: string
  exemplars: PersonaExemplar[]
  is_customized: boolean
}

// Write shape: structural server-owned fields stay out of the client contract.
export interface PersonaUpdate {
  display_name: string
  intro: string
  voice: string
  demographics: string
  values: string[]
  wants: string[]
  non_negotiables: NonNegotiableDraft[]
  polly_voice_id: string
  exemplars: { user: string; support_delta: number; note: string }[]
}

// FastAPI 422 locations look like ["body", "intro"] or
// ["body", "exemplars", 0, "support_delta"].
export interface FieldError {
  loc: (string | number)[]
  msg: string
}
