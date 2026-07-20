# Airtight POC — implementation spec

_How to build the Airtight proof-of-concept in four weeks. This is the build guide: architecture, the turn pipeline, schemas, the deterministic scoring engine, the tech stack, and a week-by-week plan. For what the product is and why, see [1-overview.md](../../plans/1-overview.md); for the scoring and anti-drift logic, [2-scoring-and-drift.md](../../plans/2-scoring-and-drift.md); for the frozen scenario, personas, and concern bank, [3-spec.md](../../plans/3-spec.md)._

**Status:** design approved 2026-07-17. Resolves the three open design questions from docs 2 and 3 (red-line mechanism, meter normalization, rubric disclosure).

---

## 1. Scope (frozen for the POC)

Exactly what the pitch commits to, nothing more:

- **One solicitation** — the five-year task order to modernize and operate a federal legacy case-management system (cloud migration, 24x7 ops, ATO, incumbent transition), authored once and frozen. Backed by two fixed reference docs: the RFP/PWS and the team's written proposal.
- **Three personas** — Dana (technical evaluator), Marcus (contracting officer), Priya (program/end-user representative), each a version-tagged markdown file with exemplars.
- **Eight frozen concerns** with a **disclosed rubric**, calibrated up front.
- **An auditable after-action report** — every point traced to a quoted span and a rubric row.

**Out of scope:** RFP ingestion, dashboards, multi-presenter, integrations, real auth. **Voice is a stretch goal**, built only if the core is done and tested (Section 9).

## 2. Design decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Deploy target | AWS commercial Bedrock; **mentor owns AWS provisioning** | Dev builds a cloud-ready, containerized, 12-factor app. GovCloud/FedRAMP path is narrated ("swap region + VPC endpoint"), not built. |
| Storage | **Postgres** (Docker local → RDS on AWS) | Durable audit trail; JSONB for extraction/score/reaction blobs. |
| Meter | **Raw 0–100 tally live, rate stats lead the report** | Matches the docs' report-first resolution to path/length-dependence. |
| Voice (stretch) | **Amazon Transcribe + Polly** | Input/output adapters around an unchanged core; transcript stays the scored artifact; on-boundary. |
| Model calls per turn | **Two** (extraction, then reaction), pure code between | Guarantees the reaction runs after the number is locked. |
| Concern sequencing | **Code-driven** (deterministic), concerns authored not generated | Keeps the POC defensible and simple; no model call decides what gets asked. |

## 3. Architecture

Three tiers. The entire product thesis is that the **middle step is code, not model**.

```
React (Vite/TS)  ──HTTP/JSON──►  FastAPI  ──boto3──►  AWS Bedrock (Claude, temp 0)
   rehearsal UI                  turn orchestrator        │  1. extraction (tool-use, forced schema)
   live per-persona meter        scoring engine (code)    │  3. reaction (after score)
   disclosed rubric panel        │                        │
   after-action report          Postgres (session + audit state)
```

**Static content is version-tagged files, loaded at startup, never in the DB.** The per-turn prompt is rebuilt from the persona file + RFP + proposal + rubric + structured session state — never from the running transcript. This is anti-drift guardrail #1 falling out of the architecture, and it is what makes a long session safe to compress.

**Boundaries (each testable in isolation):**

- **`bedrock_client`** — thin wrapper over the Bedrock Converse API. Temp 0, pinned model id, tool-use for forced schemas, one retry on schema-validation failure then fail loud. Input: prompt + tool schema. Output: validated Pydantic object.
- **`extraction` service** — builds the extraction prompt, calls `bedrock_client`, returns a validated `Extraction`.
- **`scoring` engine** — **pure functions, no I/O, no model.** Input: `Extraction` + `Rubric` + current `SessionState`. Output: `ScoreOutput`. This is where the credibility lives; it is the most-tested unit in the codebase.
- **`reaction` service** — builds the reaction prompt from persona file + computed `ScoreOutput`, returns a validated `PersonaReaction`.
- **`orchestrator`** — owns the turn lifecycle: pick concern → present → receive answer → extraction → scoring → persist → reaction → advance/follow-up. Code-driven, no model in the control flow.
- **`content` loader** — parses persona markdown (frontmatter + exemplars), `concerns.yaml`, `rubric.yaml`, and the two reference docs; validates them against schemas at startup and version-tags them.
- **`report` renderer** — code renders the scored part; one labeled model call writes the "not scored" narrative.
- **`store`** — SQLAlchemy repository over Postgres.

## 4. The turn pipeline

Every user answer moves through three steps in fixed order (docs 2, Part 1):

1. **Extraction (model, objective, temp 0, forced schema).** The model reads the answer and fills a typed checklist, quoting the user's exact words. No quote → the claim does not count. Code then computes `word_count`, `filler_ratio` (from a small filler lexicon), and `density` — these never come from the model.
2. **Scoring (code, deterministic).** The scoring engine matches the extraction against the frozen rubric and computes `support_delta` (-2..+2), `matched_rows`, and `capped`. Identical extraction in → identical number out, always.
3. **Reaction (model, subjective, temp 0).** Given the persona file *and the delta already computed*, the model writes `in_character_reply` + `rationale`. The words describe the number; they cannot set it.

## 5. Schemas (Pydantic v2)

All model outputs are forced into these via Bedrock tool-use, then validated. The JSON Schema for each is generated from the Pydantic model and passed as the tool spec. (Field definitions follow doc 2, Part 3.)

**Static / authored (loaded from files, validated at startup):**

- `PersonaDefinition` — `id`, `display_name`, `voice`, `demographics`, `values[]`, `wants[]`, `priorities[]`, `non_negotiables[]`, `rubric_version`, `exemplars[]` (`{persona, user, support_delta, note}`). Source: one markdown file per persona (frontmatter + exemplar body).
- `Concern` — `concern_id`, `core_ask`, `sub_questions[]` (`{id, text, requires: commitment|fact|fact_or_commitment}`), `red_lines[]`, `what_would_satisfy`. Source: `concerns.yaml` (8 entries).
- `Rubric` — `version:int`, `rows[]` (`{id, description, support_value}`), `cap_ceiling:int` (= **25**), row-combination rule. Source: `rubric.yaml`.

**Per-turn model output (`Extraction`):**

- `claims[]` — `{text, type: empirical_checkable|commitment|value_opinion|rhetorical, backing: bare|specified|backed|null, span}`.
- `sub_question_coverage[]` — `{id, addressed: full|partial|none, span|null}`.
- `dodges[]` — `{sub_question_id, type: topic_switch|non_commitment|deflection|pure_affect|filibuster, evidence}`.
- `consistency_flags[]` — `{conflicts_with_turn:int, detail}` (Tier-0, against the claim ledger).
- `fact_checks[]` — `{claim, tier:0|1|2, verdict: supported|refuted|unverifiable, source}` (Tier 0 = consistency, Tier 1 = RFP + proposal; Tier 2 open web is deferred).
- **`red_line_hits[]` (NEW — resolves the doc-2/3 open question)** — `{source_id, source_kind: non_negotiable|concern_red_line, span, why}`. Quote-backed. This is the field the schema was missing.
- `conciseness` — `{word_count, filler_ratio, density}` — **computed in code, not returned by the model.**

**Per-turn code output (`ScoreOutput`, produced by the scoring engine):**

- `support_delta:int` (-2..+2), `matched_rows:string[]`, `capped:bool`.

**Per-turn model output (`PersonaReaction`, second call):**

- `in_character_reply`, `rationale`.

**Session state (Postgres, not returned by any model call):** running claim ledger (verbatim spans), turn history, per-persona cumulative support + sticky cap flag, per-concern status, version tags.

## 6. The scoring engine (deterministic)

Pure code. The rubric rows and their support values (doc 2):

| Matched row | Support |
|---|---|
| Crossed a hard limit (`red_line_hit` present) | **-2 and caps the meter** |
| Dodged the main question | -2 |
| Unsubstantiated claim / generic reassurance | 0 |
| Stated fact that turned out false | -1 |
| Contradicted an earlier answer or the proposal | -1 |
| Cited a concrete, compliant approach element | +1 |
| Backed with specific staffing/schedule/past performance | +2 |

**Combination rule:** rows combine. A crossed hard limit fires first and forces the cap regardless of everything else; otherwise the matching rows are summed and clamped to [-2, +2].

**Red-line cap mechanism (resolves the open question):**

- If `extraction.red_line_hits` is non-empty → `capped = true`, `support_delta = -2`.
- Set a **sticky per-persona flag**. While set, after every subsequent turn that persona's meter is held at `min(meter, cap_ceiling)` with `cap_ceiling = 25`. Once crossed, it stays crossed — the model cannot be talked past it.

**Meter arithmetic:** per persona, start 50, apply `support_delta`, clamp [0, 100], then apply any sticky cap. The live UI shows the active persona's meter; the report shows all three.

**Determinism holds via:** forced-enum schema (almost no free text), pure arithmetic over the extraction, temp 0, a frozen version-tagged rubric, and the golden-set regression test (Section 8). The claim is *controlled, regression-tested* behavior — not bit-identical output.

## 7. Turn orchestration & session flow

Code-driven, no model in the control loop:

1. **Start session** — instantiate the frozen scenario: 3 personas, 8 concerns, rubric v1. Per-persona meters at 50, all concerns `open`.
2. **Raise a concern** — the orchestrator picks the next `open` concern by persona priority order and presents its authored `core_ask` in the persona's voice. (Verbatim `core_ask` for the POC; no generation.)
3. **Receive answer → run the pipeline** (Section 4) → persist the turn, update the claim ledger, per-persona meter, and concern status.
4. **Advance or follow up** — if sub-questions remain uncovered or a dodge was detected, the same persona pushes a follow-up on that concern (`partial`); otherwise mark `satisfied`/`dodged` and move to the next concern. A `satisfied`/`dodged` concern is not re-raised.
5. **End session** → render the after-action report.

## 8. After-action report (the deliverable)

A bright line between code and model (doc 5, "report authorship fork"):

- **Scored part — rendered by code from the extraction, `matched_rows`, and quoted spans.** Per-persona meters + cap status; coverage counts (full/partial/none); dodge count by type; contradiction count; and **rate stats that lead the report** (dodges per N turns, coverage rate, contradictions) — length-independent, per the meter decision. Every line links to its verbatim quote and rubric row. Deterministic and replayable.
- **Narrative recap — one model call, explicitly labeled "not scored"** and rendered under a visible header. Readable commentary; never feeds the number.

**Golden-set regression test (a shipped deliverable, not optional):** 15–20 hand-graded exchanges, run 3× each; assert the extraction enums and resulting `support_delta` barely move. A swing gets a new worked example added until it settles. Runs in CI on every change. This is the evidence behind the "same answer, same score" claim (doc 5, Q4).

## 9. Data model (Postgres)

Runtime state only; authored content stays in version-tagged files.

- `sessions` — `id`, `scenario_version`, `rubric_version`, `persona_ids`, `status`, `created_at`.
- `turns` — `id`, `session_id`, `turn_index`, `persona_id`, `concern_id`, `user_answer`, `extraction_json` (JSONB), `score_json` (JSONB), `reaction_json` (JSONB), `created_at`.
- `claim_ledger` — `id`, `session_id`, `turn_index`, `text`, `type`, `backing`, `span`. Feeds Tier-0 consistency; spans stored verbatim.
- `persona_meters` — `session_id`, `persona_id`, `support:int`, `capped:bool`.
- `concern_status` — `session_id`, `concern_id`, `status: open|partial|satisfied|dodged`.

## 10. Tech stack

**Must-haves:** React, FastAPI, AWS Bedrock. **Additions and why:**

| Layer | Choice | Why |
|---|---|---|
| Schema enforcement | Pydantic v2 | The "forced schema" thesis *is* Pydantic; JSON Schema drives the Bedrock tool spec, and validation is where the model's judgment gets fenced in. |
| DB access | SQLAlchemy 2.0 + Alembic | Postgres ORM + migrations. |
| DB | Postgres (Docker → RDS) | Durable audit; JSONB blobs verbatim. |
| Bedrock SDK | boto3 `bedrock-runtime` | Claude via Converse API + tool-use; temp 0; **pin the model id** (Sonnet 4.5 or newer authorized, confirmed against the FedRAMP matrix). |
| Frontend | React + Vite + TypeScript | Fast, clean chat + meter + report UI for a solo build. |
| **Styling** | **Tailwind CSS** (+ shadcn/ui, which is built on Tailwind) | **All UI styling is Tailwind utility classes — no hand-written plain CSS.** shadcn/ui gives accessible, Tailwind-styled component primitives (dialog, drawer, progress/meter, cards) to move fast solo. |
| Data fetching | TanStack Query | Session/turn state sync. |
| Tests | pytest | Scoring unit tests + the golden-set harness. |
| Quality | Ruff + mypy; ESLint + Prettier | — |
| Packaging | Docker + Docker Compose | Cloud-ready hand-off; no cloud-ops from the dev. |
| Voice (stretch) | Amazon Transcribe + Polly (boto3) | Adapters around the unchanged core. |

**Deliberately excluded (YAGNI):** real auth (single-user/shared-key for the POC), Redis, RFP ingestion, dashboards, multi-presenter.

## 11. The four-week plan

Solo build. Each week ends with something runnable and tested.

### Week 1 — Foundations + frozen content

- **Scaffold:** repo, Docker Compose (React + FastAPI + Postgres), Alembic baseline, CI (pytest + lint). Frontend initialized with **Tailwind CSS configured + shadcn/ui installed** from day one. End-to-end health check: React → FastAPI → Bedrock echo call.
- **Schemas:** all Pydantic models from Section 5; JSON-Schema generation for tool specs.
- **`bedrock_client`:** Converse + tool-use wrapper, temp 0, pinned model, validate-and-retry-once.
- **Author the frozen content** (this is real domain work, budget for it): RFP/PWS, written proposal, 3 persona files with 2–3 exemplars each, `concerns.yaml` with all 8 concerns fully filled (sub_questions + red_lines + what_would_satisfy), `rubric.yaml` v1. Content loader validates all of it at startup.

**Exit:** app boots, content validates, a hardcoded answer round-trips to Bedrock and back.

### Week 2 — Scoring core (the moat)

- **Extraction service:** prompt build, forced-schema call, validation.
- **Scoring engine:** rubric lookup, row combination, red-line cap + sticky ceiling, meter arithmetic. Pure functions, exhaustively unit-tested (every rubric row, combinations, cap stickiness, clamping).
- **Session persistence:** `store`, claim ledger, concern status, Tier-0 consistency check against the ledger.
- **Golden set:** author 15–20 hand-graded exchanges; harness runs each 3× and asserts stability.

**Exit:** given an answer, the system produces a deterministic, audited `ScoreOutput`; golden set green.

### Week 3 — Reaction + orchestration + UI

- **Reaction service:** persona rehydrated from file every turn; reply generated after the score.
- **Orchestrator:** concern selection, follow-ups on dodged/uncovered sub-questions, session lifecycle.
- **React UI (styled with Tailwind + shadcn/ui):** rehearsal chat view, live per-persona meter (shadcn progress), disclosed-rubric panel ("How you're scored" + concern core_asks + red lines, as a shadcn drawer/dialog), session start/end. No plain CSS.

**Exit:** a full text rehearsal runs end-to-end in the browser, meter moving per turn.

### Week 4 — After-action report + polish

- **Report:** code-rendered scored part (rate stats first, coverage counts, traced quotes, cap status) + labeled "not scored" model narrative; printable/exportable.
- **Hardening:** end-to-end verification, golden set green in CI, demo seed data, README + run docs, hand-off notes for the mentor's AWS deploy.
- **Buffer.**

**Exit:** demo-ready POC — start a session, rehearse against all three personas, get a defensible after-action report.

### Stretch — voice (only if the above is done and tested)

Adapters around the unchanged core (doc 3, "Post-POC: real-time voice"):

```
text  = transcribe(audio)      # NEW input adapter, before extraction
facts = model(text, persona)   # unchanged
score = apply_rubric(facts)    # unchanged: code owns the number
reply = model(facts, score)    # unchanged
speak = polly(reply)           # NEW output adapter, after the number is locked
```

Show the transcript each turn (what the scorer heard); persist audio alongside it so a disputed quote can be checked against the recording. No new scorer — voice is only an input method.

## 12. Risks & open items

- **Content authoring is the schedule risk, not the code.** The eight concerns' `red_lines` and `what_would_satisfy` must be calibrated against the exemplars (doc 3). Budget Week 1 for it; it gates the golden set in Week 2.
- **Extraction stability on hard answers.** Mitigated by the golden set — a flip is a bug fixed with a worked example, not an architecture problem (doc 5, Q4).
- **Pin the Bedrock model id** and record the FedRAMP-matrix check date; the authorized matrix changes (doc 1, open questions).
- **Voice GovCloud availability** (Transcribe/Polly) is a post-POC confirmation, not a blocker for the stretch build against commercial Bedrock.
