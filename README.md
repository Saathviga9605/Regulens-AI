# ReguLens AI

Evidence-first regulatory scrutiny assistant for AICTE Extension of Approval (EoA) applications — Smart India
Hackathon prototype. ReguLens AI supports human reviewers; it never approves or rejects applications and never
treats an anomaly as proof of misconduct.

**Current state: Deliverable 3 — secure document intake.** Users can manage fictional institutions and EoA
applications (Deliverable 2) and upload supporting PDFs to an application: files are signature-checked, hashed
(SHA-256), stored privately, flagged when they are exact duplicates, and can be opened, downloaded or deleted.
OCR, extraction, rules, verification, reports and audit are planned; see
[docs/implementation-status.md](docs/implementation-status.md).

> Document intake checks only that a file is a PDF and records its checksum. It does **not** establish that a
> document is authentic, that its issuer is legitimate, or that an application is compliant.

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

# 3. Database schema + synthetic demo data (run inside backend/ with the venv active)
cd backend
python -m app.cli migrate        # apply Alembic migrations (also runs automatically at API startup)
python -m app.cli seed           # 8 fictional institutions, 12 applications; safe to rerun
cd ..

# 4. Frontend
cd frontend
npm ci
cd ..
```

### Database commands (from `backend/`, venv active)

| Command | Effect |
|---------|--------|
| `python -m app.cli migrate` | Upgrade schema to the latest migration. Non-destructive; existing data is kept. |
| `python -m app.cli seed` | Insert the synthetic dataset. Rerunning skips existing seed records and never modifies any record. |
| `python -m app.cli seed-summary` | Print counts of institutions/applications (total, seeded, by status). |
| `python -m app.cli reset-data --confirm-reset` | **Deletes all institution, application and document data and the stored PDFs**, including records you created. Refused without the flag and outside `development`/`test`. |

Expected first `seed` output:

```
Institutions: 8 created, 0 already present
Applications: 12 created, 0 already present
{ "institutions_total": 8, "institutions_seeded": 8, "applications_total": 12, "applications_seeded": 12,
  "applications_by_status": { "draft": 4, "ready_for_preliminary_scrutiny": 2, "under_preliminary_scrutiny": 2,
                              "awaiting_additional_evidence": 2, "preliminary_scrutiny_completed": 2 } }
```

All seeded names, trusts, addresses and property identifiers are invented (trusts are suffixed "(Synthetic)",
property identifiers start with `SYN-`). No findings, documents or validation results are seeded.

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
disconnected state. **Applications** and **Institutions** in the sidebar open the management pages.

> Application statuses are internal ReguLens workflow states. Nothing is submitted to AICTE, and no status is an
> approval or rejection.

### Supporting documents

Open an application → **Supporting documents** → **Upload PDF**, choose a category and a PDF. Uploads and deletions
are allowed while the application is **Draft** or **Awaiting additional evidence**.

- **Storage**: `REGULENS_DOCUMENT_STORAGE_DIR` (default `data/documents/`, git-ignored, never served statically;
  must not be inside `frontend/`). Files are stored as `<key[:2]>/<key>.pdf` with a server-generated key —
  uploaded filenames are never used as paths. Content is only reachable through
  `GET /api/v1/documents/{id}/content`.
- **Size limit**: `REGULENS_MAX_UPLOAD_BYTES` (default 20 MiB). Only PDF is accepted (checked by `%PDF-` signature
  and `%%EOF` marker; extension and declared type are secondary signals).
- **Duplicates**: an upload with the same SHA-256 as an existing document *in the same application* is kept and
  marked *Duplicate detected* with a link to the original. Matches in other applications are shown only as a count.
- **Deletion**: explicit, confirmed, permanent (metadata + file). Deleting an original promotes its earliest
  duplicate to original. There is no audit trail yet.

Quick API check: `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
Interactive API docs (non-production only): http://127.0.0.1:8000/docs

> If port 5173 is already used by another project, Vite will exit (strict port). Run `npm run dev -- --port 5180`
> and add `http://127.0.0.1:5180` to `REGULENS_CORS_ORIGINS` in `.env`, then restart the backend.

## Test and build

```powershell
cd backend;  .\.venv\Scripts\Activate.ps1; python -m pytest; cd ..
cd frontend; npm test; npm run typecheck; npm run build; cd ..
```

Backend tests use temporary SQLite databases and temporary document storage; they never touch `data/regulens.db`
or `data/documents/`, and reset is never run against them.

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
  data/                   local SQLite database and private document storage (git-ignored)
  scripts/                reserved for future dev scripts
```

## Documentation

- [Requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [API contracts](docs/api-contracts.md)
- [Data model](docs/data-model.md)
- [Implementation status](docs/implementation-status.md)
