# Airtight

A text-based rehearsal environment for the federal-orals hot seat: a presenter answers
three frozen evaluator personas, gets a deterministic, **code-owned** score each turn, and
receives an auditable after-action report.

This is the POC monorepo scaffold (Milestone 1, Task 1). See the plan at
`../docs/superpowers/plans/2026-07-17-airtight-poc-implementation.md` and the design spec at
`../docs/superpowers/specs/2026-07-17-airtight-poc-design.md`.

## Layout

```
airtight/
├─ docker-compose.yml   # web + api + postgres
├─ .env.example         # BEDROCK_MODEL_ID, AWS_REGION, DATABASE_URL, ...
├─ server/              # FastAPI + Pydantic v2 + SQLAlchemy + Alembic
└─ frontend/            # React 18 + Vite + TS + Tailwind + TanStack Query
```

## Run everything (Docker)

```bash
cp .env.example .env      # then fill in AWS creds if running Bedrock locally
docker compose up --build
```

- API:  http://localhost:8000/health → `{"status":"ok"}`
- Web:  http://localhost:5173 (shows live API health via the `/api` proxy)

## Dev container commands

Inside the dev container, two commands are on `PATH`:

```bash
frontend    # boots Vite dev server (http://localhost:5173)
server      # boots uvicorn --reload (http://localhost:8000)
```

## Server only (local)

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v            # health test
uvicorn app.main:app --reload
```

## AWS prerequisites (Bedrock)

Any code path that calls the model needs three things in place. The variables
themselves are documented in `.env.example`.

1. `AWS_REGION` set to a region where you have Bedrock access.
2. AWS credentials resolvable from the standard chain: environment variables, a
   named profile, or an IAM role. No keys go in code.
3. Bedrock model access enabled for `BEDROCK_MODEL_ID` in that region (request it
   once from the Bedrock console under Model access).

Confirm all three with the manual smoke check:

```bash
cd server && .venv/bin/python ../scripts/smoke_bedrock.py
```

It prints a short reply containing `READY` and exits non-zero on failure. The
pytest suite never touches the network, so it passes without any of this.

## Frontend only (local)

```bash
cd frontend
npm install
npm run dev
```

## Constraints baked into this scaffold

- The model is pinned via `BEDROCK_MODEL_ID` (default Sonnet 4.5) and never computes the score.
- Every Bedrock call will set `temperature=0`.
- AWS credentials come from the environment — no keys in code.
