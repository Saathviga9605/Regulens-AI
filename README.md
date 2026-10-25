# ReguLens AI

Evidence-first regulatory scrutiny assistant for AICTE Extension of Approval (EoA) applications — Smart India
Hackathon prototype. ReguLens AI supports human reviewers; it never approves or rejects applications and never
treats an anomaly as proof of misconduct.

**Current state: Deliverable 6 — government-grade UI revamp.** The interface now uses a dedicated design system
(see [docs/design-system.md](docs/design-system.md)): a navy application shell with grouped navigation, a persistent
trust notice, accessible dialogs and confirmations, toasts, and responsive layouts from 360 px upwards. Local demo
accounts are created automatically by `seed`. Deliverable 5 delivered the reviewer workspace: on top of institution/application management, secure PDF
intake, document processing and preliminary scrutiny (Deliverables 1–4), reviewers now sign in, work from a review
queue, confirm/dismiss/escalate/resolve findings with recorded reasons, request and track additional evidence,
receive in-app alerts, download a preliminary scrutiny PDF and ask an evidence-grounded (non-AI) copilot. Important
actions are written to an application-level append-only audit log; reviewer and administrator roles are enforced by
the backend. See [docs/review-workflow.md](docs/review-workflow.md), [docs/security.md](docs/security.md),
[docs/scrutiny-and-extraction.md](docs/scrutiny-and-extraction.md) and
[docs/implementation-status.md](docs/implementation-status.md).

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
# 1. Configuration (shared by backend and frontend) — only creates .env if you don't already have one
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

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
python -m app.cli seed           # 8 fictional institutions, 12 applications + local demo accounts; safe to rerun
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

### Demo sign-in

All pages except sign-in need an account. Outside production, `python -m app.cli seed` creates (or reconciles)
two fictional local demo accounts from these `.env` settings — defaults shown, as in `.env.example`:

| Role | Username | Password |
|------|----------|----------|
| Reviewer | `demo.reviewer` | `Reviewer@Demo2026` |
| Administrator | `demo.admin` | `Admin@Demo2026` |

> **LOCAL DEMO ONLY — CHANGE BEFORE SHARING.** These credentials are public in this repository. Change
> `REGULENS_DEMO_REVIEWER_PASSWORD` / `REGULENS_DEMO_ADMIN_PASSWORD` in your `.env` (min. 10 characters) and rerun
> `python -m app.cli seed` (or `python -m app.cli create-demo-users`) before anyone else can reach the app.

- Rerunning is idempotent: only these two usernames are touched; a changed password, role or active state is
  reconciled and that account's sessions are revoked. Other accounts are never modified.
- Passwords are stored only as scrypt hashes and are never logged, audited, returned by the API or shown in the UI.
- Set `REGULENS_DEMO_USERS_ENABLED=false` to stop creating them. With `REGULENS_ENVIRONMENT=production` demo
  accounts are always off, and explicitly enabling them is rejected at startup.
- An existing `.env` without the `REGULENS_DEMO_*` keys uses the defaults above; nothing in your `.env` is overwritten.

See [docs/security.md](docs/security.md).

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

Open http://127.0.0.1:5173 and sign in. **Overview** shows live queue counts, priority applications, recent alerts
and backend status (**Connected**, **Degraded** or **Disconnected**, from the real `/api/v1/health` response). The
header carries the environment badge, alerts with unread count and the account menu (Help & About, Sign out); the
amber bar beneath it is the permanent trust notice. Below 1024 px the sidebar becomes a drawer (menu button).

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
  evidence snapshots. Uploads and deletions are recorded in the audit log.

### Demonstrating the end-to-end workflow

1. Seed (`python -m app.cli seed`), create demo users (above), start backend and frontend, open
   http://127.0.0.1:5173 and sign in as `demo.reviewer`.
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
8. **Scrutiny Rules** in the sidebar: read-only for reviewers; administrators can enable/disable rules or change
   severity (each change creates a new version).

### Reviewer workspace demo (Deliverable 5)

1. Sign in as `demo.reviewer` → **Review Queue** shows real counts; open `REG-EoA-2026-0005` and run scrutiny.
2. Open *Conflicting survey number across documents* → **Confirm finding** with a reason. Open *Conflicting built-up
   area* → **Dismiss** (a reason of ≥ 10 characters is required). The system result stays unchanged; the review
   history lists your actions.
3. *Additional evidence requests* → **New request** (e.g. "Structural stability certificate").
4. *Supporting documents* → **Upload PDF**, choose *Structural Stability Certificate*, and select the request under
   *Link to evidence request*. Then in the request: **Mark fulfilled** → **Confirm fulfilled**.
5. *Activity* (bottom of the page) shows the audit entries; **Alerts** in the sidebar shows the generated alerts —
   mark them read.
6. *Reviewer copilot* → "Why was the survey number conflict raised?" — the answer cites rule CON-003 and quotes
   "Survey No.: 312" / "Survey No.: 318"; click a source to open the finding.
7. *Preliminary scrutiny* → **Download preliminary report** (PDF).
8. Sign out, sign in as `demo.admin`: toggle a rule on **Scrutiny Rules**, create a user on **Users**, review the
   global **Audit Trail**. As `demo.reviewer` those pages/operations are refused (403).

Quick API check: `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
Interactive API docs (non-production only): http://127.0.0.1:8000/docs

> If port 5173 is already used by another project, Vite will exit (strict port). Run `npm run dev -- --port 5180`
> and add `http://127.0.0.1:5180` to `REGULENS_CORS_ORIGINS` in `.env`, then restart the backend.

## Test and build

```powershell
cd backend;  .\.venv\Scripts\Activate.ps1; python -m pytest; cd ..
cd frontend; npm test; npm run typecheck; npm run build; npm audit; cd ..
```

### UI smoke test (real browser, optional)

`frontend/e2e/smoke.mjs` drives the running app in Microsoft Edge (via `playwright-core`, no browser download):
sign-in, overview, queue, scrutiny and a finding action, upload and confirmed delete, copilot, report download,
reviewer permission denial, admin rule and user confirmations, the audit trail, an overflow sweep at
360/390/768/1024/1440/1920 px and the mobile drawer. **It writes data**, so run it against a scratch database on
spare ports, never your working data:

```powershell
# Terminal A (backend/, venv active): scratch database on port 8030
$env:REGULENS_DATABASE_URL = "sqlite:///$env:TEMP/regulens-smoke.db"
$env:REGULENS_DOCUMENT_STORAGE_DIR = "$env:TEMP/regulens-smoke-docs"
$env:REGULENS_CORS_ORIGINS = "http://127.0.0.1:5195"
python -m app.cli migrate; python -m app.cli seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8030

# Terminal B (frontend/)
$env:VITE_API_BASE_URL = "http://127.0.0.1:8030/api/v1"; npx vite --port 5195 --strictPort --host 127.0.0.1

# Terminal C (frontend/)
$env:SMOKE_ALLOW_WRITES = "1"; $env:SMOKE_BASE_URL = "http://127.0.0.1:5195"; $env:SMOKE_API_URL = "http://127.0.0.1:8030/api/v1"
npm run smoke
```

Screenshots go to `data/smoke-screenshots/` (git-ignored; override with `SMOKE_OUT_DIR`). Without
`SMOKE_ALLOW_WRITES=1` the script refuses to run. Use `SMOKE_BROWSER_CHANNEL=chrome` for Chrome.

Backend tests use temporary SQLite databases and temporary document storage; they never touch `data/regulens.db`
or `data/documents/`, and reset is never run against them. They need no network access. The real-Tesseract test
is skipped when Tesseract is not installed; OCR-unavailable behaviour and the OCR code path (with a stub engine) are
always tested.

### Local OCR (optional, Deliverable 8)

Scanned and photographed pages need a local OCR engine. Either install Tesseract (see "OCR setup on Windows" above)
or the CPU-only RapidOCR engine into the venv (models ship inside the wheel; nothing is downloaded at run time):

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
pip install -r requirements-ocr.txt
pip install --no-deps rapidocr-onnxruntime==1.2.3   # --no-deps: avoids pulling a second OpenCV build
```

`REGULENS_OCR_ENGINE=auto` (default) uses Tesseract if found, else RapidOCR, else none; set `tesseract`,
`rapidocr` or `none` to choose explicitly. The cross-case panel and `/api/v1/system/info` show what is available.
Evaluate with and without OCR: `python -m app.cli reuse-eval --out ..\docs\evaluation\reuse-d8` and
`python -m app.cli reuse-eval --no-ocr --out ..\docs\evaluation\reuse-d8-no-ocr`. See
[docs/ai-document-understanding.md](docs/ai-document-understanding.md).

### Cross-case reuse demo (Deliverable 7)

```powershell
cd backend
python -m app.cli reuse-fixtures --load                    # four fictional cases A–D (idempotent)
python -m app.cli reuse-scan --application <code of case A>  # printed by the previous command
python -m app.cli grant-cross-case --username demo.reviewer  # or use the Users page as admin
python -m app.cli reuse-eval --out ..\docs\evaluation\reuse-d7   # A0/A1/A4 metrics (JSON, CSV, Markdown)
python -m app.cli reuse-fixtures --reset --confirm-reset    # removes only the fixture cases (dev/test)
```

Case B holds a rescaled copy of case A's certificate (transformed positive); case D uses the same template with a
different institution (hard negative); case C is a raster scan (stays a candidate without OCR). Open case A →
"Cross-case reuse" → "Open comparison" (requires the cross-case reviewer permission). See
[docs/reuse-detection.md](docs/reuse-detection.md).

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
- [Reviewer workflow (review states, evidence requests, alerts, report, copilot)](docs/review-workflow.md)
- [Security, roles and audit](docs/security.md)
- [Design system (tokens, components, layout, accessibility)](docs/design-system.md)
- [Cross-case document reuse (cascade, permissions, evaluation)](docs/reuse-detection.md)
- [Local OCR, evidence fusion and explanations (what is OCR, CV, rules or a model)](docs/ai-document-understanding.md)
- [Deliverable 9 acceptance: checklist, status mapping, migration and demo steps](docs/d9-acceptance.md)
- [Implementation status](docs/implementation-status.md)
