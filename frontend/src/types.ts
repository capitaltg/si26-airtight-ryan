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
  concern_id: string
  prompt: string
  is_follow_up: boolean
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
  matched_rows: string[]
  meter: number
  capped: boolean
  meters: Meter[]
  next_prompt: Prompt | null
  done: boolean
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
}

export interface ConcernDisclosure {
  concern_id: string
  core_ask: string
  what_would_satisfy: string
  red_lines: string[]
}

export interface RubricDisclosure {
  version: number
  rows: RubricRow[]
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

export interface ScoredFinding {
  turn_index: number
  persona_id: string
  concern_id: string
  rubric_row: string
  support_value: number
  span: string // verbatim quote
  detail: string
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
  clarifications: ClarificationLine[]
  narrative: NarrativeSection
}

// A single completed exchange as accumulated client-side for the transcript.
// Built from the prompt shown plus the AnswerResponse it produced.
export interface TranscriptTurn {
  key: number // stable, append-only order key for React lists
  personaId: string
  concernId: string
  isFollowUp: boolean
  prompt: string
  answer: string
  reply: string
  rationale: string
  supportDelta: number
  matchedRows: string[]
  capped: boolean
  // A clarification turn is not scored: ChatTurn branches on this to suppress the
  // delta badge and rubric chips. Absent/true means a normal scored turn.
  scored?: boolean
}
