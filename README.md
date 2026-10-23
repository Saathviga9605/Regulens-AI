# ReguLens AI

Evidence-first regulatory scrutiny assistant for AICTE Extension of Approval (EoA) applications — Smart India
Hackathon prototype. ReguLens AI supports human reviewers; it never approves or rejects applications and never
treats an anomaly as proof of misconduct.

**Current state: Deliverable 4 — document intelligence and preliminary scrutiny.** On top of institution/application
management and secure PDF intake, ReguLens extracts page text (OCR when Tesseract is installed), detects document
types, extracts evidence-quoted fields, runs configurable deterministic rules and cross-document checks, raises
anomaly indicators, performs **simulated** issuer checks against synthetic records, and keeps a history of scrutiny
runs and findings for human review. Reports, audit trail and authentication are planned; see
[docs/implementation-status.md](docs/implementation-status.md) and
[docs/scrutiny-and-extraction.md](docs/scrutiny-and-extraction.md).

> Findings are preliminary indicators for a human reviewer. Nothing in ReguLens approves or rejects an application,
> establishes that a document is authentic, or concludes misconduct. Default expectation rules are **demo-only** and
> not verified against official AICTE sources. Issuer checks are **SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY**.

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
| `python -m app.cli reset-data --confirm-reset` | **Deletes all institution, application, document, processing, scrutiny-run and synthetic issuer-reference data and the stored PDFs**, including records you created (scrutiny rules are kept). Refused without the flag and outside `development`/`test`. |

Expected first `seed` output:

```
Institutions: 8 created, 0 already present
Applications: 12 created, 0 already present
{ "institutions_total": 8, "institutions_seeded": 8, "applications_total": 12, "applications_seeded": 12,
  "applications_by_status": { "draft": 4, "ready_for_preliminary_scrutiny": 2, "under_preliminary_scrutiny": 2,
                              "awaiting_additional_evidence": 2, "preliminary_scrutiny_completed": 2 } }
```

The seed also adds **12 fictional demo PDFs** to three draft applications (each PDF is bannered "FICTIONAL
DEMONSTRATION DOCUMENT - NOT A GENUINE CERTIFICATE") and **4 synthetic issuer reference records**, and prints
`Demo documents: 12 created …`. All names, trusts, addresses, certificate numbers and authorities are invented.
No findings or processing results are seeded — they are produced by running the pipeline. Reseeding never modifies
existing records; demo documents are skipped if their application is no longer accepting documents.

### OCR setup on Windows (optional)

Text-based PDFs need nothing extra. For scanned (image-only) pages install Tesseract, e.g.
`winget install UB-Mannheim.TesseractOCR` (or the installer from the UB Mannheim Tesseract wiki), then restart the
backend. ReguLens auto-detects `tesseract` on `PATH` or `C:\Program Files\Tesseract-OCR\tesseract.exe`; otherwise set
`REGULENS_TESSERACT_CMD` in `.env`. Without Tesseract, image-only pages are reported as *Too little text (OCR not
available)* and the document's processing status is *failed* with code `ocr_unavailable` — never as an empty success.
The backend logs a warning at startup when OCR is unavailable.

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
  duplicate to original. Processing results are removed with the document; past scrutiny findings keep their
  evidence snapshots. There is no audit trail yet.

### Demonstrating the end-to-end workflow

1. Seed (`python -m app.cli seed`), start backend and frontend, open http://127.0.0.1:5173.
2. **Applications** → open `REG-EoA-2026-0005` (Hooghly Riverside, the inconsistent demo; codes are for a fresh
   database — check the seed output / list otherwise).
3. *Supporting documents* → **Process all**. Open **Details** on `occupancy-certificate.pdf` to see detected type,
   extracted fields with quoted evidence and page numbers, and **Show extracted page text**.
4. In the same details panel click **Run simulated issuer check** → *Simulated mismatch*, labelled
   SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY.
5. *Preliminary scrutiny* → **Run preliminary scrutiny**. Expect: conflicting survey number (312 vs 318), conflicting
   built-up area, stated validity date passed, missing structural stability certificate (demo-only rule), exact
   duplicate indicator. Click a finding to see its explanation, evidence quotes, rule source and demo-only label; set a
   human review status.
6. **Rerun** and use the *Scrutiny run* selector to view earlier runs.
7. Open `REG-EoA-2026-0001` (clean demo): run scrutiny → *No findings*; the fire certificate's simulated check →
   *Simulated match*. Open `REG-EoA-2026-0008` for unreadable/miscategorised examples.
8. **Scrutiny Rules** in the sidebar: enable/disable rules or change severity (each change creates a new version).

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
or `data/documents/`, and reset is never run against them. They need no network access. The real-Tesseract test
is skipped when Tesseract is not installed; OCR-unavailable behaviour and the OCR code path (with a stub engine) are
always tested.

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
- [Document intelligence and scrutiny (pipeline, rules, limitations)](docs/scrutiny-and-extraction.md)
- [Implementation status](docs/implementation-status.md)
