# AGENTS.md

Guidance for Claude Code (and any agent) working in this repo.

## Always-on skills

Use these on every task in this project, without being asked:

- **superpowers** — invoke relevant skills before acting. Brainstorm before design, follow TDD when writing code, use systematic-debugging on bugs, write/execute plans for multi-step work. When several apply, process skills set the approach first, then implementation skills carry it out.
- **caveman (full)** — reply in caveman full mode. Drop articles, filler, and pleasantries; fragments are fine. Code, commits, PRs, and security or destructive-action warnings stay in normal prose.
- **humanizer** — run any prose you produce (docs, comments, PR text, reports) through the humanizer patterns before finishing. No em dashes, no rule-of-three padding, no promotional filler.

Skill precedence still holds: direct user instructions and this file override skills, which override default behavior.

## Templates

When a task says to use a template, follow that template exactly. Do not restructure it, drop sections, or add your own. If the template does not fit the situation, say so and ask before deviating.

Templates live in `docs/templates/`:

- `PR_TEMPLATE.md` — pull-request writeups. The GitHub-rendered copy at `.github/PULL_REQUEST_TEMPLATE.md` mirrors it; keep both in sync.
- `ISSUE_TEMPLATE_CLAUDE.md` — issue writeups.
- `TASK_TEMPLATE.md` — a single implementation task, in the plan's TDD shape.

## What Airtight is

Airtight is a text rehearsal environment for the US federal-orals "hot seat". A proposal team practices the live evaluator Q&A of an oral proposal against three fixed AI evaluator personas, and gets a score on what they actually said, defensible line by line.

The core thesis: **code owns the score, the model does not.** A chatbot improvises a grade in the same breath as its reply and gives a different number next time. Airtight splits the turn so the number comes from deterministic code, not model judgment:

```
facts = model(answer, persona)   # model ONLY classifies into a quote-backed checklist
score = apply_rubric(facts)      # plain code: deterministic, replayable, version-tagged
reply = model(facts, score)      # persona reacts AFTER the number is locked
```

Same answer scores the same twice, and every point traces to a rubric row and a verbatim quote. That defensibility is the product, not a detail.

This is a roughly one-month AI capstone at Capital Technology Group. It is a POC, deliberately narrow: one frozen solicitation, three personas (Dana/technical, Marcus/contracting officer, Priya/program rep), eight frozen concerns, a disclosed rubric, and an auditable after-action report. Out of scope: RFP ingestion, dashboards, multi-presenter, real auth. Voice (Transcribe + Polly around the unchanged core) is the top stretch goal, built only if the core is done and tested.

## Where the design lives

Read these before touching design decisions. Do not re-derive what they already settle.

- `docs/superpowers/plans/2026-07-17-airtight-poc-implementation.md` — the task-by-task build plan (milestones, files, interfaces, TDD steps). **Source of truth for what to build next.**
- `docs/superpowers/specs/2026-07-17-airtight-poc-design.md` — architecture, turn pipeline, schemas, scoring engine, tech stack, four-week plan.
- `docs/plans/0-pitch.md` — one-page pitch.
- `docs/plans/1-overview.md` — product, problem, buyer, "why not a chatbot".
- `docs/plans/2-scoring-and-drift.md` — scoring mechanics and anti-drift logic.
- `docs/plans/3-spec.md` — the frozen scenario, personas, concern bank.
- `docs/plans/4-chatbot-comparison.md` — why prompting a chatbot cannot match this.
- `docs/plans/5-reviewer-qa.md` — reviewer Q&A.
- `docs/ideation/` — earlier ideation notes (superseded by the plans above).

Note: the design docs still say `backend/`; the actual Python package lives in `server/`. Trust the tree below over the docs on paths.

## Locked constraints (from the plan — do not break)

- **Model pinned and config-driven.** `BEDROCK_MODEL_ID`, default `anthropic.claude-sonnet-4-5-20250929`. Sonnet 4.5 because it still accepts `temperature=0` (Sonnet 5 / Opus 4.8 return 400 on `temperature`) and is FedRAMP-High-authorized in GovCloud. Do NOT swap to a 4.6+/5 model without removing every `temperature=0`.
- **Every Bedrock call sets `temperature=0`.**
- **The model never computes the number.** Extraction classifies into enums with required quotes; pure Python owns `support_delta`, `matched_rows`, `capped`; reaction runs after the number exists. Any code that lets a model emit the score is a defect.
- **Extraction is forced via tool-use**, validated with Pydantic, retried once, then fails loud. Never feed unvalidated model JSON to the scorer.
- **Red-line cap = 25**, sticky per persona. Once crossed, that persona's meter is held at `min(meter, 25)` for the rest of the session.
- **Meter starts at 50, clamps to [0,100], per persona.** Report leads with length-independent rate stats.
- **Authored content is version-tagged and file-based**, validated at startup, never stored in the DB, rehydrated into every prompt (anti-drift guardrail #1).
- **Verbatim spans everywhere.** Quotes stored exactly as returned; no summarization of scored artifacts.
- **AWS credentials come from the environment.** No keys in code.
- **The scoring engine is the moat** — pure functions, no I/O, exhaustively unit-tested. It gets the most rigorous TDD.

## Project structure

<!-- STRUCTURE:START -->
```
airtight/
├─ .devcontainer/
│  ├─ bin/
│  │  ├─ frontend
│  │  └─ server
│  ├─ devcontainer.json
│  ├─ docker-compose.yml
│  └─ Dockerfile
├─ .github/
│  ├─ ISSUE_TEMPLATE/
│  │  └─ task.md
│  ├─ workflows/
│  │  ├─ e2e.yml                 # runs e2e on every push + PR
│  │  ├─ frontend.yml            # oxlint + oxfmt + build/typecheck (on frontend changes)
│  │  └─ server.yml              # ruff + mypy + pytest (on server changes)
│  └─ PULL_REQUEST_TEMPLATE.md
├─ e2e/                          # Playwright e2e smoke tests (boots stack via docker compose)
│  ├─ tests/
│  │  ├─ a11y-contrast.spec.ts   # axe-core WCAG 2.1 AA color-contrast check
│  │  └─ health.spec.ts
│  ├─ .gitignore
│  ├─ package-lock.json
│  ├─ package.json
│  ├─ playwright.config.ts
│  └─ README.md
├─ frontend/                     # React 18 + Vite + TS + Tailwind + TanStack Query
│  ├─ src/
│  │  ├─ App.tsx
│  │  ├─ index.css
│  │  ├─ main.tsx
│  │  └─ vite-env.d.ts
│  ├─ .dockerignore
│  ├─ Dockerfile
│  ├─ index.html
│  ├─ package-lock.json
│  ├─ package.json
│  ├─ postcss.config.js
│  ├─ tailwind.config.js
│  ├─ tsconfig.json
│  ├─ tsconfig.node.json
│  └─ vite.config.ts
├─ scripts/
│  ├─ smoke_bedrock.py
│  └─ update_structure.py
├─ server/                       # FastAPI + Pydantic v2 + SQLAlchemy + Alembic
│  ├─ alembic/
│  │  ├─ versions/
│  │  │  └─ 0001_init.py
│  │  ├─ env.py
│  │  └─ script.py.mako
│  ├─ app/
│  │  ├─ bedrock/
│  │  │  ├─ __init__.py
│  │  │  └─ client.py
│  │  ├─ content/
│  │  │  ├─ store/
│  │  │  │  ├─ personas/
│  │  │  │  │  ├─ contracting_officer.md
│  │  │  │  │  ├─ program_rep.md
│  │  │  │  │  └─ technical_evaluator.md
│  │  │  │  ├─ concerns.yaml
│  │  │  │  ├─ rfp_pws.md
│  │  │  │  ├─ rubric.yaml
│  │  │  │  └─ written_proposal.md
│  │  │  ├─ __init__.py
│  │  │  └─ loader.py
│  │  ├─ db/
│  │  │  ├─ __init__.py
│  │  │  ├─ models.py
│  │  │  └─ repo.py
│  │  ├─ pipeline/
│  │  │  ├─ __init__.py
│  │  │  ├─ conciseness.py
│  │  │  ├─ extraction.py
│  │  │  └─ scoring.py
│  │  ├─ schemas/
│  │  │  ├─ __init__.py
│  │  │  ├─ content.py
│  │  │  ├─ extraction.py
│  │  │  ├─ reaction.py
│  │  │  └─ scoring.py
│  │  ├─ __init__.py
│  │  ├─ config.py               # pydantic-settings
│  │  └─ main.py                 # FastAPI app + /health
│  ├─ tests/
│  │  ├─ golden/
│  │  │  ├─ __init__.py
│  │  │  ├─ cases.yaml
│  │  │  └─ test_golden.py
│  │  ├─ __init__.py
│  │  ├─ test_api.py
│  │  ├─ test_bedrock_client.py
│  │  ├─ test_conciseness.py
│  │  ├─ test_content_loader.py
│  │  ├─ test_extraction.py
│  │  ├─ test_extraction_schema.py
│  │  ├─ test_repo.py
│  │  └─ test_scoring.py
│  ├─ .dockerignore
│  ├─ alembic.ini
│  ├─ Dockerfile
│  └─ pyproject.toml             # deps + ruff + mypy + pytest config
├─ .env.example                  # BEDROCK_MODEL_ID, AWS_REGION, DATABASE_URL, ...
├─ .gitignore
├─ .lintstagedrc.json
├─ .oxfmtrc.json
├─ .oxlintrc.json
├─ AGENTS.md                     # this file
├─ commitlint.config.mjs
├─ docker-compose.yml            # web + api + postgres
├─ lefthook.yml
├─ package-lock.json
├─ package.json
└─ README.md                     # run/setup instructions
```
<!-- STRUCTURE:END -->

**Keep this tree current.** Whenever you add, remove, rename, or move a file or directory in this repo, update the block between the `STRUCTURE:START` and `STRUCTURE:END` markers in the same change, before you finish the task. The tree lists real files, not planned ones. When a directory fills with routine files (many schemas, components, tests), a one-line summary is fine instead of every filename. The full planned layout lives in the implementation plan; this block reflects what actually exists now.

## Stack and commands

Backend (`server/`): FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, `anthropic[bedrock]`, Postgres 16. Tests: pytest. Lint/types: Ruff + mypy (strict).

Frontend (`frontend/`): React 18, Vite, TypeScript, Tailwind, TanStack Query (shadcn/ui to be added). All UI styling is Tailwind utility classes, no hand-written CSS.

```bash
# everything
docker compose up --build              # API :8000, web :5173

# server only
cd server && pip install -e ".[dev]"
pytest -v                              # golden set auto-skips without AWS creds
ruff check . && mypy app
uvicorn app.main:app --reload

# frontend only
cd frontend && npm install && npm run dev
npm run build                          # type-checks

# e2e (Playwright, drives the running stack)
cd e2e && npm install
npm run install:browsers               # first time only: downloads Chromium
npm run e2e                            # boots stack, waits, tests, tears down
npm test                               # tests only, against an already-running stack

# repo root tooling
npm run lint        # oxlint
npm run format      # oxfmt --write
```

## CI (GitHub Actions)

Three workflows run on push and PR:

- `server.yml` — ruff, mypy (strict), pytest. Path-filtered to `server/**`.
- `frontend.yml` — oxlint, oxfmt check, build + typecheck. Path-filtered to `frontend/**` and shared lint/format config.
- `e2e.yml` — boots the stack with docker compose, waits for both services, runs Playwright, uploads the HTML report. Runs on all changes.

The frontend workflow scopes oxlint/oxfmt to `frontend/` (repo-wide format is not enforced in CI yet; the pre-commit hook formats staged JS/TS). `.oxfmtrc.json` sets `semi: false` to match the codebase style.

Commits use Conventional Commits (enforced by commitlint via the lefthook `commit-msg` hook). Run `npm run prepare` once after cloning to wire up git hooks.
