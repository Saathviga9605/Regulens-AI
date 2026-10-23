# ReguLens AI

Evidence-first regulatory scrutiny assistant for AICTE Extension of Approval (EoA) applications — Smart India
Hackathon prototype. ReguLens AI supports human reviewers; it never approves or rejects applications and never
treats an anomaly as proof of misconduct.

**Current state: Deliverable 1 — runnable full-stack foundation.** A FastAPI backend with a live SQLite health
check, and a React dashboard shell that shows the real backend status. Business features (uploads, OCR, rules,
verification, reports, audit) are planned; see [docs/implementation-status.md](docs/implementation-status.md).

## Prerequisites (Windows)

- Python 3.11+ (verified with 3.13) — `python --version`
- Node.js 20+ with npm (verified with Node 24 / npm 11) — `node --version`
- PowerShell. If script activation is blocked, run once:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

No Docker, PostgreSQL or external services are required.

## Setup

From the repository root (`regulens-ai/`):

```powershell
# 1. Configuration (shared by backend and frontend)
Copy-Item .env.example .env

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.lock.txt
pip install -e ".[dev]"
cd ..

# 3. Frontend
cd frontend
npm ci
cd ..
```

## Run (two terminals)

```powershell
# Terminal 1 — backend on http://127.0.0.1:8000
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — frontend on http://127.0.0.1:5173
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. The sidebar and Dashboard show **Connected**, **Degraded** or **Disconnected**
based on the actual `/api/v1/health` response. Stop the backend and press **Retry** to see the
disconnected state.

Quick API check: `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
Interactive API docs (non-production only): http://127.0.0.1:8000/docs

> If port 5173 is already used by another project, Vite will exit (strict port). Run `npm run dev -- --port 5180`
> and add `http://127.0.0.1:5180` to `REGULENS_CORS_ORIGINS` in `.env`, then restart the backend.

## Test and build

```powershell
cd backend;  .\.venv\Scripts\Activate.ps1; python -m pytest; cd ..
cd frontend; npm test; npm run typecheck; npm run build; cd ..
```

Backend tests use temporary SQLite databases and never touch `data/regulens.db`.

## Configuration

All settings live in `.env` at the repo root; see [.env.example](.env.example) for documented defaults.
Backend variables are prefixed `REGULENS_`; the frontend reads `VITE_API_BASE_URL`.

## Repository layout

```
regulens-ai/
  CLAUDE.md               conventions for Claude Code sessions
  .env.example            documented configuration
  docs/                   requirements, architecture, API contracts, data model, status
  backend/                FastAPI app (app/) + pytest suite (tests/)
  frontend/               React + Vite app (src/) + Vitest suite (tests/)
  data/                   local SQLite database (git-ignored)
  scripts/                reserved for future dev scripts
```

## Documentation

- [Requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [API contracts](docs/api-contracts.md)
- [Data model](docs/data-model.md)
- [Implementation status](docs/implementation-status.md)
