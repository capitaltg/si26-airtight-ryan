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

// --- disclosed rubric panel (GET /content/rubric) ---

export interface RubricRow {
  id: string
  description: string
  support_value: number
}

export interface ConcernDisclosure {
  concern_id: string
  core_ask: string
  what_would_satisfy: string
  red_lines: string[]
}

export interface RubricDisclosure {
  version: number
  cap_ceiling: number
  rows: RubricRow[]
  concerns: ConcernDisclosure[]
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
}
