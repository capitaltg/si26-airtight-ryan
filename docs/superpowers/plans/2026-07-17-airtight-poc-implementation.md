# Airtight POC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 4-week Airtight POC — a text-based rehearsal environment where a presenter answers three frozen federal-orals evaluator personas, gets a deterministic, code-owned score each turn, and receives an auditable after-action report.

**Architecture:** Three tiers. React (Vite + TS + Tailwind + shadcn/ui) talks to FastAPI over JSON. FastAPI runs the per-turn pipeline: a Bedrock **extraction** call (forced JSON schema, temp 0) → pure-Python **scoring engine** (rubric lookup + red-line cap + meter arithmetic) → a Bedrock **reaction** call (persona reply, generated *after* the number is locked). Postgres holds runtime session/audit state; authored content (RFP, proposal, 3 personas, 8 concerns, rubric) lives in version-tagged files loaded at startup and rehydrated into every prompt (this is anti-drift guardrail #1). The whole app is Dockerized and 12-factor so the mentor can deploy it to AWS unchanged.

**Tech Stack:** React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query (frontend); FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic (backend); Postgres 16; `anthropic[bedrock]` (`AnthropicBedrockMantle` client) targeting `anthropic.claude-sonnet-4-5-20250929`; pytest + Ruff + mypy; Docker Compose. Voice stretch: `boto3` Amazon Transcribe + Polly.

## Global Constraints

- **Model is pinned and config-driven.** `BEDROCK_MODEL_ID` env var, default `anthropic.claude-sonnet-4-5-20250929`. Sonnet 4.5 because it (a) still accepts `temperature=0` (Sonnet 5 / Opus 4.8 return 400 on `temperature`), and (b) is the model named FedRAMP-High-authorized in GovCloud in the security docs. Do NOT swap to a 4.6+/5 model without removing every `temperature=0`.
- **Every Bedrock call sets `temperature=0`.** Determinism does not *rest* on this (doc 5 Q4) — it rests on forced-schema + the golden set — but temp 0 is one stabilizer and Sonnet 4.5 supports it.
- **The model never computes the number.** Extraction classifies into enums with required quotes; pure Python owns `support_delta`, `matched_rows`, `capped`; reaction runs after the number exists. Any code that lets a model emit the score is a defect.
- **Extraction output is forced via tool-use** (`tool_choice: {"type":"tool","name":"emit_extraction"}`), validated with Pydantic, retried **once** on validation failure, then fails loud. Never accept unvalidated model JSON into the scorer.
- **Red-line cap ceiling = 25**, sticky per-persona, config value in `rubric.yaml` (`cap_ceiling: 25`). Once a persona's red line is crossed, that persona's meter is held at `min(meter, 25)` for the rest of the session.
- **Meter starts at 50, clamps to [0,100], per persona.** Report leads with length-independent rate stats.
- **Authored content is version-tagged and file-based**, validated against Pydantic schemas at startup; never stored in the DB; rehydrated into every prompt.
- **Verbatim spans everywhere.** Quotes for claims, coverage, red-line hits, and the claim ledger are stored exactly as returned — the audit trail depends on it. No summarization of scored artifacts.
- **AWS credentials come from the environment** (standard AWS credential chain / IAM role). No keys in code. The mentor owns the AWS account and deploy; the dev builds a container that reads creds from the environment.
- Design source of truth: `docs/superpowers/specs/2026-07-17-airtight-poc-design.md` (§5 schemas, §6 scoring, §8 report). Product/scoring detail: `docs/plans/1-overview.md`, `docs/plans/2-scoring-and-drift.md`, `docs/plans/3-spec.md`.

---

## Context

Airtight (formerly "Cogent") is rchan's ~1-month AI capstone at Capital Technology Group. The design is approved and specced; this plan turns spec §11 (the four-week plan) into task-level work. The repo currently holds only planning docs under `docs/` — this is a greenfield build and **not yet a git repository** (Task 1 initializes it). The novel, defensibility-critical part is the deterministic scoring engine and the forced-schema extraction that feeds it; those get the most rigorous TDD. Boilerplate (CRUD routers, UI components) is specified by pattern. Content authoring (the RFP, personas, concerns, rubric) is real govcon domain work and is the schedule risk — it is front-loaded into Week 1 because it gates the Week 2 golden set.

---

## Repository Structure

```
airtight/
├─ docker-compose.yml            # web + api + postgres
├─ .env.example                  # BEDROCK_MODEL_ID, AWS_REGION, DATABASE_URL, ...
├─ backend/
│  ├─ pyproject.toml             # deps + ruff + mypy + pytest config
│  ├─ alembic.ini, alembic/      # migrations
│  ├─ app/
│  │  ├─ main.py                 # FastAPI app, startup content load, routers
│  │  ├─ config.py               # pydantic-settings: env + paths
│  │  ├─ schemas/                # Pydantic v2 models (one file per object group)
│  │  │  ├─ content.py           #   PersonaDefinition, Concern, SubQuestion, Rubric
│  │  │  ├─ extraction.py        #   Extraction + nested blocks (tool schema source)
│  │  │  ├─ scoring.py           #   ScoreOutput
│  │  │  └─ reaction.py          #   PersonaReaction
│  │  ├─ content/
│  │  │  ├─ loader.py            # parse+validate persona md / concerns.yaml / rubric.yaml
│  │  │  └─ store/               # THE AUTHORED CONTENT (version-tagged)
│  │  │     ├─ rfp_pws.md, written_proposal.md
│  │  │     ├─ personas/{technical_evaluator,contracting_officer,program_rep}.md
│  │  │     ├─ concerns.yaml, rubric.yaml
│  │  ├─ bedrock/
│  │  │  └─ client.py            # AnthropicBedrockMantle wrapper: forced tool, validate+retry
│  │  ├─ pipeline/
│  │  │  ├─ extraction.py        # build prompt, call bedrock, return Extraction
│  │  │  ├─ conciseness.py       # word_count / filler_ratio / density (CODE, no model)
│  │  │  ├─ scoring.py           # THE MOAT: pure functions, no I/O
│  │  │  ├─ reaction.py          # build prompt (persona + score), return PersonaReaction
│  │  │  └─ orchestrator.py      # turn lifecycle + concern selection
│  │  ├─ db/
│  │  │  ├─ models.py            # SQLAlchemy: sessions, turns, claim_ledger, persona_meters, concern_status
│  │  │  └─ repo.py              # repository functions
│  │  ├─ report/
│  │  │  └─ builder.py           # code-rendered scored report + one labeled model narrative
│  │  └─ api/
│  │     ├─ sessions.py          # POST /sessions, GET /sessions/{id}, POST /sessions/{id}/answer, POST /sessions/{id}/end, GET report
│  │     └─ content.py           # GET /content/rubric (disclosed rubric panel)
│  └─ tests/
│     ├─ test_scoring.py         # exhaustive scoring-engine unit tests
│     ├─ test_extraction_schema.py
│     ├─ test_conciseness.py
│     ├─ golden/                 # 15-20 hand-graded exchanges + harness
│     │  ├─ cases.yaml
│     │  └─ test_golden.py
│     └─ test_api.py
└─ frontend/
   ├─ package.json, vite.config.ts, tailwind.config.js, components.json (shadcn)
   └─ src/
      ├─ api/client.ts           # typed fetch + TanStack Query hooks
      ├─ types.ts                # TS mirrors of API DTOs
      ├─ components/{Rehearsal,MeterBar,RubricPanel,ChatTurn,AfterActionReport}.tsx
      └─ App.tsx, main.tsx
```

---

# Milestone 1 — Foundations + frozen content (Week 1)

**Exit:** app boots via `docker compose up`, content validates at startup, a hardcoded answer round-trips React → FastAPI → Bedrock and back.

### Task 1: Repo, tooling, and Docker Compose skeleton

**Files:**
- Create: `airtight/.gitignore`, `airtight/docker-compose.yml`, `airtight/.env.example`, `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/config.py`, `frontend/` (via `npm create vite`)

**Interfaces:**
- Produces: `GET /health` → `{"status":"ok"}`; `config.settings` (pydantic-settings) exposing `bedrock_model_id`, `aws_region`, `database_url`, `content_dir`.

- [ ] **Step 1: Initialize git and scaffold.** From `airtight/`: `git init`; scaffold FastAPI (`pyproject.toml` with `fastapi`, `uvicorn[standard]`, `anthropic[bedrock]`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pydantic-settings`, `pyyaml`, `python-frontmatter`; dev: `pytest`, `ruff`, `mypy`), and `npm create vite@latest frontend -- --template react-ts`.
- [ ] **Step 2: Write the failing health test.**
```python
# backend/tests/test_api.py
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```
- [ ] **Step 3: Run it, confirm it fails** (`app.main` import error). Run: `cd backend && pytest tests/test_api.py -v`.
- [ ] **Step 4: Implement `config.py` + minimal `main.py`.**
```python
# backend/app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bedrock_model_id: str = "anthropic.claude-sonnet-4-5-20250929"
    aws_region: str = "us-east-1"
    database_url: str = "postgresql+psycopg://airtight:airtight@localhost:5432/airtight"
    content_dir: Path = Path(__file__).parent / "content" / "store"

settings = Settings()
```
```python
# backend/app/main.py
from fastapi import FastAPI
app = FastAPI(title="Airtight")

@app.get("/health")
def health():
    return {"status": "ok"}
```
- [ ] **Step 5: Run the test, confirm pass.** Run: `pytest tests/test_api.py -v`.
- [ ] **Step 6: Write `docker-compose.yml`** (services: `postgres:16` with volume, `api` building `backend/` running uvicorn, `web` building `frontend/`), and `.env.example` documenting every var. Add CI later; commit.
- [ ] **Step 7: Commit.** `git add -A && git commit -m "chore: scaffold airtight monorepo with health check"`

### Task 2: Pydantic schemas for all objects

**Files:**
- Create: `backend/app/schemas/content.py`, `extraction.py`, `scoring.py`, `reaction.py`
- Test: `backend/tests/test_extraction_schema.py`

**Interfaces:**
- Produces (consumed by every later task): `PersonaDefinition`, `Concern`, `SubQuestion`, `Rubric`, `RubricRow`; `Extraction` with nested `Claim`, `SubQuestionCoverage`, `Dodge`, `ConsistencyFlag`, `FactCheck`, `RedLineHit`, `Conciseness`; `ScoreOutput`; `PersonaReaction`. Field definitions per spec §5.
- Key enums: `ClaimType = empirical_checkable|commitment|value_opinion|rhetorical`; `Backing = bare|specified|backed`; `Addressed = full|partial|none`; `DodgeType = topic_switch|non_commitment|deflection|pure_affect|filibuster`; `RedLineSourceKind = non_negotiable|concern_red_line`; `Requires = commitment|fact|fact_or_commitment`.

- [ ] **Step 1: Write failing tests** asserting (a) a valid `Extraction` dict parses, (b) a `Claim` with `type="commitment"` requires `backing`, (c) `RedLineHit` requires `source_id` + `span`, (d) `Extraction.model_json_schema()` returns a dict with `red_line_hits` in properties.
- [ ] **Step 2: Run, confirm fail.** Run: `pytest tests/test_extraction_schema.py -v`.
- [ ] **Step 3: Implement schemas.** Example (extraction.py — write the rest to match spec §5):
```python
# backend/app/schemas/extraction.py
from enum import Enum
from pydantic import BaseModel, Field

class ClaimType(str, Enum):
    empirical_checkable = "empirical_checkable"; commitment = "commitment"
    value_opinion = "value_opinion"; rhetorical = "rhetorical"
class Backing(str, Enum):
    bare = "bare"; specified = "specified"; backed = "backed"

class Claim(BaseModel):
    text: str
    type: ClaimType
    backing: Backing | None = None
    span: str  # verbatim quote from the answer
# ... SubQuestionCoverage, Dodge, ConsistencyFlag, FactCheck, RedLineHit per spec §5

class RedLineHit(BaseModel):
    source_id: str
    source_kind: str  # "non_negotiable" | "concern_red_line"
    span: str
    why: str

class Extraction(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    sub_question_coverage: list["SubQuestionCoverage"] = Field(default_factory=list)
    dodges: list["Dodge"] = Field(default_factory=list)
    consistency_flags: list["ConsistencyFlag"] = Field(default_factory=list)
    fact_checks: list["FactCheck"] = Field(default_factory=list)
    red_line_hits: list[RedLineHit] = Field(default_factory=list)
    # conciseness is computed in code and attached after, NOT part of the tool schema
```
```python
# backend/app/schemas/scoring.py
from pydantic import BaseModel
class ScoreOutput(BaseModel):
    support_delta: int      # -2..+2
    matched_rows: list[str]
    capped: bool
```
- [ ] **Step 4: Run tests, confirm pass.** Run: `pytest tests/test_extraction_schema.py -v`.
- [ ] **Step 5: Commit.** `git commit -am "feat: pydantic schemas for content, extraction, scoring, reaction"`

### Task 3: Content loader + authored content

**Files:**
- Create: `backend/app/content/loader.py`; all files under `backend/app/content/store/`
- Test: `backend/tests/test_content_loader.py`

**Interfaces:**
- Consumes: schemas from Task 2.
- Produces: `load_content() -> Content` where `Content` bundles `rfp_text: str`, `proposal_text: str`, `personas: dict[str, PersonaDefinition]`, `concerns: dict[str, Concern]`, `rubric: Rubric`. Called once at FastAPI startup; raises on any validation failure (fail-fast).

- [ ] **Step 1: Author the frozen content** (domain work — budget real time; drafts exist in `docs/plans/3-spec.md`):
  - `rfp_pws.md`, `written_proposal.md` — the synthetic case-management-modernization solicitation + the team's written proposal (label synthetic).
  - `personas/*.md` — frontmatter (`id`, `display_name`, `voice`, `demographics`, `values`, `wants`, `priorities`, `non_negotiables`, `rubric_version`) + body with 2–3 exemplars each (`{persona, user, support_delta, note}`). Seed from spec §"three evaluator personas".
  - `concerns.yaml` — all 8 concerns (`technical_approach`, `key_personnel`, `transition`, `past_performance`, `cost_realism`, `compliance_security`, `operational_impact`, `risk`), each with `core_ask`, `sub_questions[]` (`id`, `text`, `requires`), `red_lines[]`, `what_would_satisfy`. Seed the table from spec §"concern bank".
  - `rubric.yaml` — `version: 1`, `cap_ceiling: 25`, and `rows[]` mirroring spec §6 (id, description, support_value): `red_line`(-2/cap), `dodge`(-2), `unsubstantiated`(0), `false_fact`(-1), `contradiction`(-1), `approach_cited`(+1), `evidence_backed`(+2).
- [ ] **Step 2: Write failing test** asserting `load_content()` returns 3 personas, 8 concerns, `rubric.version == 1`, `rubric.cap_ceiling == 25`, and that a deliberately malformed persona file raises.
- [ ] **Step 3: Run, confirm fail.** Run: `pytest tests/test_content_loader.py -v`.
- [ ] **Step 4: Implement loader** using `python-frontmatter` for personas and `yaml.safe_load` for concerns/rubric; validate each into its Pydantic model; assemble `Content`.
- [ ] **Step 5: Run, confirm pass.** Run: `pytest tests/test_content_loader.py -v`.
- [ ] **Step 6: Wire into startup** — load content in a FastAPI lifespan handler, stash on `app.state.content`. Extend `test_api.py` to assert the app starts with content loaded.
- [ ] **Step 7: Commit.** `git commit -am "feat: authored POC content + fail-fast content loader"`

### Task 4: Bedrock client wrapper (forced schema, validate + retry)

**Files:**
- Create: `backend/app/bedrock/client.py`
- Test: `backend/tests/test_bedrock_client.py`

**Interfaces:**
- Produces: `extract(prompt: str, *, content_schema: type[BaseModel], tool_name: str) -> BaseModel` (forces the tool, validates, retries once) and `react(prompt: str) -> str` (plain text reply). Both set `temperature=0`, `model=settings.bedrock_model_id`. The Bedrock call is injected/mockable so tests never hit the network.

- [ ] **Step 1: Write failing tests** with a fake Bedrock transport: (a) `extract` returns a validated model instance when the fake returns valid tool input; (b) `extract` retries exactly once then raises `ExtractionValidationError` when the fake returns invalid JSON twice; (c) both calls pass `temperature=0` and the configured model id.
- [ ] **Step 2: Run, confirm fail.** Run: `pytest tests/test_bedrock_client.py -v`.
- [ ] **Step 3: Implement wrapper.**
```python
# backend/app/bedrock/client.py
from anthropic import AnthropicBedrockMantle
from pydantic import BaseModel, ValidationError
from app.config import settings

class ExtractionValidationError(RuntimeError): ...

class BedrockClient:
    def __init__(self, transport=None):
        self._c = transport or AnthropicBedrockMantle(aws_region=settings.aws_region)

    def extract(self, prompt, *, content_schema, tool_name, max_tokens=4096):
        tool = {"name": tool_name, "description": "Emit the structured extraction.",
                "input_schema": content_schema.model_json_schema()}
        last = None
        for _ in range(2):  # initial + one retry
            resp = self._c.messages.create(
                model=settings.bedrock_model_id, max_tokens=max_tokens, temperature=0,
                tools=[tool], tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            try:
                return content_schema.model_validate(block.input)
            except (ValidationError, AttributeError) as e:
                last = e
        raise ExtractionValidationError(str(last))

    def react(self, prompt, *, max_tokens=1024):
        resp = self._c.messages.create(
            model=settings.bedrock_model_id, max_tokens=max_tokens, temperature=0,
            messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in resp.content if b.type == "text")
```
- [ ] **Step 4: Run, confirm pass.** Run: `pytest tests/test_bedrock_client.py -v`.
- [ ] **Step 5: Manual smoke test (real Bedrock, requires AWS creds).** Add `scripts/smoke_bedrock.py` that calls `react("Say READY.")` and prints the result; run once with creds available. Document in README that this needs `AWS_REGION` + credentials and Bedrock model access enabled.
- [ ] **Step 6: Commit.** `git commit -am "feat: bedrock client with forced-schema extraction and validate-retry"`

---

# Milestone 2 — Scoring core, the moat (Week 2)

**Exit:** given an `Extraction` + `Rubric` + prior meter state, the engine produces a deterministic, audited `ScoreOutput`; conciseness computed in code; session state persists; golden set green.

### Task 5: Conciseness (pure code, no model)

**Files:** Create `backend/app/pipeline/conciseness.py`; Test `backend/tests/test_conciseness.py`

**Interfaces:** Produces `compute_conciseness(answer_text: str, extraction: Extraction) -> Conciseness` with `word_count:int`, `filler_ratio:float` (0–1 over a small filler lexicon), `density:float` (substantive_claims / sentences).

- [ ] **Step 1: Write failing tests** — empty string → 0s; a padded sentence → filler_ratio > 0; density = substantive claims (non-`rhetorical`/`value_opinion`) over sentence count.
- [ ] **Step 2: Run, confirm fail.** Run: `pytest tests/test_conciseness.py -v`.
- [ ] **Step 3: Implement** with a module-level `FILLER = {"um","uh","basically","honestly","you know","like","actually",...}`, whitespace tokenization, and sentence split on `[.!?]`.
- [ ] **Step 4: Run, confirm pass.** Run: `pytest tests/test_conciseness.py -v`.
- [ ] **Step 5: Commit.** `git commit -am "feat: code-computed conciseness signals"`

### Task 6: The deterministic scoring engine

**Files:** Create `backend/app/pipeline/scoring.py`; Test `backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: `Extraction`, `Rubric`.
- Produces: `score_turn(extraction: Extraction, rubric: Rubric) -> ScoreOutput` and `apply_to_meter(current: int, delta: int, capped: bool, cap_ceiling: int, already_capped: bool) -> tuple[int, bool]` returning `(new_meter, sticky_capped)`. Pure functions, no I/O, no model.

**Rubric combination rule (spec §6):** if `red_line_hits` non-empty → `capped=True`, `support_delta=-2`, `matched_rows=["red_line"]` (fires first, ignores other rows). Otherwise sum matched rows and clamp to [-2,+2]. Matched rows: `dodge`(-2) if any dodge; `false_fact`(-1) per `fact_check.verdict=="refuted"`; `contradiction`(-1) if any `consistency_flag`; `evidence_backed`(+2) if any commitment claim has `backing=="backed"`; `approach_cited`(+1) if any coverage is `full`/`partial` with a compliant cited element and not already counted as backed; `unsubstantiated`(0) otherwise.

- [ ] **Step 1: Write the failing test suite** (this is the most important test file — be exhaustive):
```python
# backend/tests/test_scoring.py  (representative cases; add one per rubric row + combinations)
from app.pipeline.scoring import score_turn, apply_to_meter
from app.schemas.extraction import Extraction, RedLineHit, Dodge, Claim

def _rubric():
    from app.content.loader import load_content
    return load_content().rubric  # version 1, cap_ceiling 25

def test_red_line_fires_first_and_caps():
    ext = Extraction(red_line_hits=[RedLineHit(source_id="marcus_pws", source_kind="non_negotiable",
                                               span="we'll also do X outside scope", why="promised work outside PWS")],
                     # even a strong backed claim present:
                     claims=[Claim(text="PM has 12 yrs", type="commitment", backing="backed", span="...")])
    out = score_turn(ext, _rubric())
    assert out.capped is True and out.support_delta == -2 and out.matched_rows == ["red_line"]

def test_backed_commitment_scores_plus_two():
    ext = Extraction(claims=[Claim(text="staffed by 3 named leads", type="commitment", backing="backed", span="...")])
    assert score_turn(ext, _rubric()).support_delta == 2

def test_dodge_scores_minus_two():
    ext = Extraction(dodges=[Dodge(sub_question_id="staffing", type="non_commitment", evidence="answered with enthusiasm")])
    assert score_turn(ext, _rubric()).support_delta == -2

def test_rows_combine_and_clamp():
    # +1 approach cited AND -1 contradiction => net 0; verify clamp never exceeds [-2,2]
    ...

def test_meter_starts_50_clamps_and_cap_is_sticky():
    m, capped = apply_to_meter(68, -2, capped=True, cap_ceiling=25, already_capped=False)
    assert m == 25 and capped is True
    m2, capped2 = apply_to_meter(25, +2, capped=False, cap_ceiling=25, already_capped=True)  # good answer after cap
    assert m2 == 25 and capped2 is True  # ceiling holds
    assert apply_to_meter(50, +2, False, 25, False) == (52, False)
    assert apply_to_meter(1, -2, False, 25, False) == (0, False)  # clamp floor
```
- [ ] **Step 2: Run, confirm fail.** Run: `pytest tests/test_scoring.py -v`.
- [ ] **Step 3: Implement `scoring.py`** — pure functions matching the combination rule above; `apply_to_meter` does `new = clamp(current + delta, 0, 100)`, then `sticky = already_capped or capped`, then if `sticky: new = min(new, cap_ceiling)`.
- [ ] **Step 4: Run, confirm pass.** Run: `pytest tests/test_scoring.py -v`.
- [ ] **Step 5: Commit.** `git commit -am "feat: deterministic scoring engine with sticky red-line cap"`

### Task 7: DB models, migrations, repository, extraction service + Tier-0 consistency

**Files:** Create `backend/app/db/models.py`, `db/repo.py`, `alembic/versions/0001_init.py`, `backend/app/pipeline/extraction.py`; Test `backend/tests/test_repo.py`

**Interfaces:**
- Produces DB tables: `sessions`(id, scenario_version, rubric_version, persona_ids, status, created_at), `turns`(id, session_id, turn_index, persona_id, concern_id, user_answer, extraction_json JSONB, score_json JSONB, reaction_json JSONB, created_at), `claim_ledger`(id, session_id, turn_index, text, type, backing, span), `persona_meters`(session_id, persona_id, support, capped), `concern_status`(session_id, concern_id, status).
- Produces `run_extraction(answer, concern, persona, content, prior_claims) -> Extraction`: builds the extraction prompt (persona file + RFP + proposal + concern object + prior claim ledger for Tier-0 consistency), calls `BedrockClient.extract`, attaches code-computed `conciseness`.

- [ ] **Step 1: Write failing repo test** (uses a transactional Postgres test DB or SQLite fallback) — create a session, append a turn with JSONB blobs, read it back verbatim; append claims to the ledger and fetch by session.
- [ ] **Step 2: Run, confirm fail.** Run: `pytest tests/test_repo.py -v`.
- [ ] **Step 3: Implement models + Alembic migration + repo functions.** Use SQLAlchemy 2.0 typed `Mapped[...]`; JSONB columns store the Pydantic `.model_dump()` of extraction/score/reaction.
- [ ] **Step 4: Run, confirm pass.** Run: `pytest tests/test_repo.py -v`.
- [ ] **Step 5: Implement `extraction.py`** — the prompt builder rehydrates the persona markdown, RFP, proposal, the active concern object, and the running claim ledger (verbatim spans) so Tier-0 contradictions can be detected; returns a fully-populated `Extraction`. Unit-test the prompt builder (string contains persona voice, concern core_ask, and prior claim spans) with a fake BedrockClient.
- [ ] **Step 6: Commit.** `git commit -am "feat: persistence layer, claim ledger, extraction service with tier-0 rehydration"`

### Task 8: Golden-set regression harness

**Files:** Create `backend/tests/golden/cases.yaml`, `backend/tests/golden/test_golden.py`

**Interfaces:** 15–20 hand-graded `{concern_id, persona_id, answer, expected_support_delta, expected_capped, expected_matched_rows}` cases. Harness runs each **3×** against real Bedrock extraction → scoring and asserts the score is stable and matches the hand grade.

- [ ] **Step 1: Author 15–20 cases** covering every rubric row and at least 2 red-line crossings and 2 contradictions. Store expected values from your own domain judgment.
- [ ] **Step 2: Write the harness** — for each case, run `run_extraction` + `score_turn` three times; assert all three `support_delta`/`capped`/`matched_rows` are equal to each other (stability) and equal to the expected (validity). Mark it `@pytest.mark.golden` and skip when `AWS_REGION`/creds are absent so unit CI stays offline-green.
- [ ] **Step 3: Run against real Bedrock.** Run: `pytest tests/golden -m golden -v`. For any case that swings, add a worked exemplar to the relevant persona file and re-run until it settles (per doc 2 "golden-set" method). Log any case you cannot stabilize.
- [ ] **Step 4: Commit.** `git commit -am "test: golden-set regression harness for extraction+scoring stability"`

---

# Milestone 3 — Reaction, orchestration, UI (Week 3)

**Exit:** a full text rehearsal runs end-to-end in the browser, meter moving per turn, disclosed rubric visible.

### Task 9: Reaction service (persona reply after the score)

**Files:** Create `backend/app/pipeline/reaction.py`; Test `backend/tests/test_reaction.py`

**Interfaces:** Produces `run_reaction(persona, concern, extraction, score: ScoreOutput, content) -> PersonaReaction`. The prompt is rebuilt fresh from the persona file every turn (anti-drift #1) and is given the already-computed `support_delta`/`matched_rows` so the reply describes the number, never sets it.

- [ ] **Step 1: Write failing test** (fake BedrockClient) asserting the reaction prompt contains the persona voice + the computed delta and matched rows, and that `run_reaction` returns a validated `PersonaReaction` (`in_character_reply`, `rationale`).
- [ ] **Step 2: Run, confirm fail; Step 3: implement; Step 4: run, confirm pass.** Run: `pytest tests/test_reaction.py -v`.
- [ ] **Step 5: Commit.** `git commit -am "feat: persona reaction generated after the number is locked"`

### Task 10: Turn orchestrator + session API

**Files:** Create `backend/app/pipeline/orchestrator.py`, `backend/app/api/sessions.py`, `backend/app/api/content.py`; Test `backend/tests/test_orchestrator.py`

**Interfaces:**
- `orchestrator.start_session(content) -> Session` (meters at 50, all concerns `open`).
- `orchestrator.next_concern(session) -> Concern | None` (deterministic: next `open` concern by persona priority order; `None` when exhausted).
- `orchestrator.submit_answer(session, answer) -> TurnResult` (runs extraction → scoring → persist → meter update → reaction; advances or issues a same-concern follow-up when sub-questions are uncovered or a dodge was detected; sets concern status open/partial/satisfied/dodged).
- API: `POST /sessions` (create + first concern), `GET /sessions/{id}`, `POST /sessions/{id}/answer` `{answer}` → `{reply, rationale, meter, capped, next_prompt, done}`, `POST /sessions/{id}/end`, `GET /sessions/{id}/report`, `GET /content/rubric`.

- [ ] **Step 1: Write failing orchestrator tests** (fake BedrockClient with scripted extractions): a dodge yields a follow-up on the same concern and drops the meter; a backed answer satisfies the concern and advances; a red-line answer caps and stays capped across the next good answer; session ends after 8 concerns satisfied/dodged.
- [ ] **Step 2: Run, confirm fail.** Run: `pytest tests/test_orchestrator.py -v`.
- [ ] **Step 3: Implement orchestrator + routers.** Concern selection is code-driven (no model in the control loop). Wire routers into `main.py`.
- [ ] **Step 4: Run, confirm pass; add `test_api.py` coverage** for the answer round-trip with a fake client injected via dependency override.
- [ ] **Step 5: Commit.** `git commit -am "feat: code-driven turn orchestrator + session/content API"`

### Task 11: React rehearsal UI (Tailwind + shadcn/ui)

**Files:** Create `frontend/src/api/client.ts`, `types.ts`, `components/{Rehearsal,MeterBar,RubricPanel,ChatTurn}.tsx`, wire `App.tsx`; `tailwind.config.js` + `components.json`

**Interfaces:** Consumes the session API. `MeterBar` uses shadcn `Progress`; `RubricPanel` uses shadcn `Sheet`/`Dialog`; chat is a scrollable transcript. TanStack Query mutation for `submit answer`.

- [ ] **Step 1: Install + init** Tailwind and shadcn/ui (`npx shadcn@latest init`; add `button`, `progress`, `dialog`/`sheet`, `card`, `textarea`). All styling is Tailwind utility classes — no hand-written CSS.
- [ ] **Step 2: Build `types.ts`** mirroring the API DTOs and `api/client.ts` (typed `fetch` + `useMutation`/`useQuery` hooks).
- [ ] **Step 3: Build components** — `Rehearsal` (persona name + current prompt, answer `Textarea`, submit), `ChatTurn` (presenter answer + persona reply + rationale), `MeterBar` (per-persona `Progress`, red when `capped`), `RubricPanel` ("How you're scored" drawer: rubric rows + each concern's `core_ask` / `what_would_satisfy` / `red_lines` from `GET /content/rubric`).
- [ ] **Step 4: Manual verify end-to-end** — `docker compose up`, start a session in the browser, answer 2–3 concerns, watch the meter move and a red-line answer pin the meter. (Use the `run` skill / drive the app.)
- [ ] **Step 5: Commit.** `git commit -am "feat: react rehearsal UI with live meter and disclosed rubric panel"`

---

# Milestone 4 — After-action report + polish (Week 4)

**Exit:** demo-ready — start a session, rehearse all three personas, get a defensible after-action report.

### Task 12: After-action report (code-rendered scored part + labeled model narrative)

**Files:** Create `backend/app/report/builder.py`; extend `GET /sessions/{id}/report`; Create `frontend/src/components/AfterActionReport.tsx`; Test `backend/tests/test_report.py`

**Interfaces:** `build_report(session, turns, content) -> Report` where the **scored part is 100% code-rendered** from stored extractions/`matched_rows`/spans: per-persona meters + cap status; coverage counts (full/partial/none); dodge count by type; contradiction count; and **rate stats lead** (dodges per N turns, coverage rate). Every scored line links to its verbatim quote + rubric row. Then **one** Bedrock `react` call produces a short narrative recap under a visible **"Not scored"** header; it never feeds any number.

- [ ] **Step 1: Write failing test** — given persisted turns, assert the report's counts equal the hand-computed counts, that every scored line carries a non-empty `span`, that the narrative is present and tagged `scored=False`, and that regenerating the scored part twice from the same turns is byte-identical (deterministic).
- [ ] **Step 2: Run, confirm fail; Step 3: implement; Step 4: run, confirm pass.** Run: `pytest tests/test_report.py -v`.
- [ ] **Step 5: Build `AfterActionReport.tsx`** — rate stats first, then per-persona meters, coverage/dodge/contradiction tables with expandable quotes, cap banner, and the clearly-labeled "Not scored" narrative. Add a print stylesheet (Tailwind `print:` utilities) so it exports via the browser.
- [ ] **Step 6: Commit.** `git commit -am "feat: auditable after-action report, code-rendered with labeled narrative"`

### Task 13: Hardening, seed, docs, deploy hand-off

**Files:** `backend/tests/` (fill coverage gaps), `README.md`, `scripts/seed_demo.py`, CI workflow, `DEPLOY.md`

- [ ] **Step 1: End-to-end verification** — run the full flow in the browser; confirm the golden set is green against real Bedrock; run `ruff`, `mypy`, and the full `pytest` suite.
- [ ] **Step 2: Seed script** — `scripts/seed_demo.py` creates a demo session so the app opens ready to show.
- [ ] **Step 3: README + DEPLOY.md** — local `docker compose up`, env vars, Bedrock model-access prerequisite, and a hand-off note for the mentor's AWS deploy (container reads AWS creds from the environment/IAM role; swap `DATABASE_URL` to RDS, `BEDROCK_MODEL_ID` stays pinned; GovCloud path = same image, different region + VPC endpoint — narrated, not built).
- [ ] **Step 4: CI** — GitHub Actions running `ruff` + `mypy` + offline `pytest` (golden set skipped without creds).
- [ ] **Step 5: Commit + finish the branch** (superpowers:finishing-a-development-branch).

---

# Stretch — Voice (only if Milestones 1–4 are done and tested)

Adapters around the unchanged core (spec §9). Build as: `POST /sessions/{id}/answer_audio` accepts audio → **Amazon Transcribe** (`boto3`) → transcript → the **same** `run_extraction`/`score_turn`/`run_reaction` pipeline → **Amazon Polly** synthesizes `in_character_reply` to audio. Show the transcript each turn (what the scorer heard) and persist the audio alongside it so a disputed quote can be checked. No new scorer. Confirm Transcribe/Polly GovCloud availability before pitching it as accredited (post-POC item).

---

# Verification

- **Unit/offline (every task):** `cd backend && pytest -v` (golden set auto-skipped without AWS creds); `ruff check .`; `mypy app`. Frontend: `npm run build` type-checks.
- **Scoring determinism (the moat):** `pytest tests/test_scoring.py -v` must be exhaustive and green — this is the defensibility claim in code.
- **Golden set (needs AWS creds + Bedrock access):** `pytest tests/golden -m golden -v` — extraction+score stable across 3 runs and matching hand grades.
- **End-to-end (real app):** `docker compose up`, open the web app, start a session, and (a) give a backed answer → meter rises; (b) dodge → meter drops + follow-up on the same concern; (c) cross a red line → persona meter pinned ≤ 25 for the rest of the session; (d) end the session → after-action report shows rate stats first, every scored line has a verbatim quote, and the model narrative sits under a "Not scored" header. Use the `run`/`verify` skills to drive and observe this.
- **Deploy-readiness:** `docker compose up` from a clean checkout with only `.env` populated must boot the full stack; no hardcoded endpoints or credentials.
