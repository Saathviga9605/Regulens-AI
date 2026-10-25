# ReguLens AI

**Evidence-first regulatory scrutiny assistance for AICTE Extension of Approval (EoA) applications.**

ReguLens AI helps scrutiny reviewers examine EoA applications and their supporting documents. It reads uploaded
certificates (including scanned and photographed copies), extracts critical fields with quoted, page-referenced
evidence, checks applications against configurable rules, detects possible reuse of the same document across
different applications, and records every reviewer decision in an audit trail.

> [!IMPORTANT]
> ReguLens AI is **decision support, not decision making**. It never approves or rejects an application, never
> establishes that a document is authentic, and never treats an anomaly or a similarity as proof of misconduct.
> Every finding requires human review. ReguLens AI is an independent prototype and is not an AICTE service.

---

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the application](#running-the-application)
- [Accounts and roles](#accounts-and-roles)
- [Configuration](#configuration)
- [Command-line reference](#command-line-reference)
- [Guided walkthrough](#guided-walkthrough)
- [Testing and quality](#testing-and-quality)
- [Evaluation](#evaluation)
- [Security and privacy](#security-and-privacy)
- [Limitations](#limitations)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)

---

## Capabilities

| Area | What ReguLens AI does |
|---|---|
| **Case management** | Institutions and EoA applications with declared programmes, internal workflow states and an institution snapshot captured when an application is marked ready. |
| **Secure document intake** | PDF-only uploads with signature checks, size limits, SHA-256 integrity, duplicate detection and private storage. Files are never served statically. |
| **Document understanding** | Text-layer extraction; local OCR for scanned and photographed pages with per-line confidence and coordinates; document-type classification; extraction of critical fields (institution, certificate number, issuing authority, dates, survey and property identifiers, address, area), each with a quoted source line, page number and location. |
| **Preliminary scrutiny** | Configurable, versioned, deterministic rules and anomaly detectors. Each finding carries its explanation, evidence and rule provenance. Production rules are the default; demonstration rule sets must be selected explicitly. |
| **Source verification** | A replaceable issuer-verification interface. The only adapter included is a **simulated** registry; results are always labelled with their source type (`SIMULATED` or `NOT_CONNECTED`). |
| **Cross-case reuse detection** | A multi-stage cascade (exact hash, text similarity, perceptual page hashing, geometric verification with difference regions, critical-field comparison, evidence fusion) that surfaces pairs of documents from different applications that may share underlying content, with a traceable explanation. |
| **Reviewer workspace** | Review queue, finding actions with mandatory reasons, evidence requests, in-app alerts, preliminary scrutiny reports (PDF) and an append-only audit trail. |
| **Access control** | Reviewer and administrator roles enforced server-side, plus a separate, explicitly granted permission for cross-case evidence. |

### Outcome vocabularies

ReguLens keeps independent concepts separate, so a reviewer is never asked to read one as another:

| Dimension | Values |
|---|---|
| Cross-case reuse outcome | `MATCH_CONFIRMED_FOR_REVIEW`, `CANDIDATE`, `NOT_MATCHED`, `INCONCLUSIVE` |
| Source-verification status | Verified, Mismatch detected, Expired, Verification pending, Source unavailable, Manual review required |
| Source type | `LIVE` (reserved; no live integration exists), `SIMULATED`, `NOT_CONNECTED` |
| Evidence state | extracted, not found, ambiguous, unverified |
| Reviewer disposition | recorded per finding and per document pair, with actor, reason and timestamp |

---

## Architecture

```
┌──────────────────────────┐      HTTPS / JSON (bearer token)      ┌───────────────────────────────────┐
│  React + TypeScript SPA  │  ───────────────────────────────────▶ │  FastAPI  /api/v1                  │
│  Vite · Tailwind design  │                                        │  ├─ auth, roles, audit             │
│  system · Vitest         │  ◀─────────────────────────────────── │  ├─ intake & private storage       │
└──────────────────────────┘                                        │  ├─ processing: PyMuPDF, local OCR │
                                                                    │  ├─ scrutiny rules & findings      │
                                                                    │  ├─ cross-case reuse (OpenCV)      │
                                                                    │  └─ reports, alerts, evaluation    │
                                                                    └──────────────┬────────────────────┘
                                                                                   │ SQLAlchemy 2 · Alembic
                                                                         ┌─────────▼─────────┐
                                                                         │ SQLite  +  private │
                                                                         │ document storage   │
                                                                         └────────────────────┘
```

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite |
| Document processing | PyMuPDF; OCR via Tesseract or RapidOCR (PP-OCR models on ONNX Runtime, CPU) |
| Computer vision | OpenCV (ORB features, RANSAC homography, ECC alignment), NumPy |
| Frontend | React 18, TypeScript (strict), Vite, Tailwind CSS v4, React Router |
| Testing | pytest, Vitest + Testing Library, Playwright (Edge) smoke test |

All analysis runs locally. No paid API, API key, cloud inference or network call is used, and no model weights are
downloaded at run time. See [docs/architecture.md](docs/architecture.md).

---

## Requirements

- Windows 10/11 with PowerShell (other platforms work with equivalent shell commands)
- Python 3.11 or newer (verified with 3.13)
- Node.js 20 or newer with npm (verified with Node 24 / npm 11)
- No GPU, Docker, database server or external service is required

If PowerShell blocks virtual-environment activation, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## Installation

From the repository root:

```powershell
# 1. Configuration (creates .env only if it does not exist; never overwrites your settings)
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.lock.txt
pip install -e ".[dev]"

# 3. Database schema and synthetic demonstration data
python -m app.cli migrate
python -m app.cli seed
cd ..

# 4. Frontend
cd frontend
npm ci
cd ..
```

`seed` is idempotent: it inserts 8 fictional institutions, 12 applications, 12 bannered demonstration PDFs, 4
synthetic issuer reference records and the local demonstration accounts. Re-running never modifies existing records.

### Optional: local OCR

Text-based PDFs need no OCR. To read scanned or photographed pages, install **one** local engine:

```powershell
# Option A — RapidOCR (installed into the backend virtual environment; CPU only)
cd backend; .\.venv\Scripts\Activate.ps1
pip install -r requirements-ocr.txt
pip install --no-deps rapidocr-onnxruntime==1.2.3

# Option B — Tesseract (system-wide; requires an administrator installer)
winget install UB-Mannheim.TesseractOCR
```

`REGULENS_OCR_ENGINE=auto` (default) uses Tesseract if found, otherwise RapidOCR, otherwise none. Without an engine,
image-only pages are reported as unreadable (`ocr_unavailable`) — never as an empty success. The active engine is
shown in the application and at `GET /api/v1/system/info`.

---

## Running the application

```powershell
# Terminal 1 — API on http://127.0.0.1:8000
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — web application on http://127.0.0.1:5173
cd frontend
npm run dev
```

Open **http://127.0.0.1:5173** and sign in.

- Health check: `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
- Interactive API documentation (non-production only): http://127.0.0.1:8000/docs
- If port 5173 is taken, run `npm run dev -- --port 5180` and add `http://127.0.0.1:5180` to `REGULENS_CORS_ORIGINS`.

> [!NOTE]
> The API applies pending database migrations at start-up. Before upgrading an existing installation, back up the
> database: `Copy-Item data\regulens.db data\regulens.backup.db`.

---

## Accounts and roles

Outside production, `seed` creates two local demonstration accounts from `.env`:

| Role | Username | Default password |
|---|---|---|
| Reviewer | `demo.reviewer` | `Reviewer@Demo2026` |
| Administrator | `demo.admin` | `Admin@Demo2026` |

> [!WARNING]
> **Local demonstration only.** These defaults are public. Change `REGULENS_DEMO_REVIEWER_PASSWORD` and
> `REGULENS_DEMO_ADMIN_PASSWORD` in `.env` and re-run `python -m app.cli seed` before anyone else can reach the
> application. Demonstration accounts are always disabled when `REGULENS_ENVIRONMENT=production`.

| Capability | Reviewer | Administrator | Cross-case reviewer permission |
|---|:-:|:-:|:-:|
| Applications, documents, scrutiny, findings, evidence requests, reports | ✓ | ✓ | — |
| Start cross-case scans; see restricted reuse alerts | ✓ | ✓ | — |
| Open cross-case pairs, linked-case details, page images, record pair decisions | — | — | required |
| Manage rules and users; view the global audit trail | — | ✓ | — |
| Run and export reuse evaluations | — | ✓ | or this permission |

The cross-case permission is granted per user by an administrator (Users page, or
`python -m app.cli grant-cross-case --username <name>`). Administrators cannot grant it to themselves.

---

## Configuration

All settings are read from `.env` at the repository root (see [.env.example](.env.example)). Backend variables use
the `REGULENS_` prefix; the frontend reads `VITE_API_BASE_URL`.

| Variable | Default | Purpose |
|---|---|---|
| `REGULENS_ENVIRONMENT` | `development` | `development`, `test`, `staging` or `production` |
| `REGULENS_DATABASE_URL` | `sqlite:///data/regulens.db` | Database location |
| `REGULENS_DOCUMENT_STORAGE_DIR` | `data/documents` | Private document storage (never inside `frontend/`) |
| `REGULENS_MAX_UPLOAD_BYTES` | `20971520` | Maximum upload size (20 MiB) |
| `REGULENS_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed browser origins |
| `REGULENS_OCR_ENGINE` | `auto` | `auto`, `tesseract`, `rapidocr` or `none` |
| `REGULENS_OCR_ENABLED` | `true` | Disable OCR entirely |
| `REGULENS_TESSERACT_CMD` | *(auto-detect)* | Path to `tesseract.exe` if not on `PATH` |
| `REGULENS_OCR_DPI` | `200` | Render resolution for OCR |
| `REGULENS_SESSION_TTL_MINUTES` | `480` | Session lifetime |
| `REGULENS_LOGIN_MAX_FAILURES` / `REGULENS_LOGIN_LOCKOUT_MINUTES` | `5` / `15` | Sign-in lockout policy |
| `REGULENS_DEMO_USERS_ENABLED` | `true` | Create local demonstration accounts (ignored in production) |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | API base URL used by the web application |

---

## Command-line reference

Run from `backend/` with the virtual environment active: `python -m app.cli <command>`.

| Command | Description |
|---|---|
| `migrate` | Apply database migrations (non-destructive). |
| `seed` | Insert synthetic demonstration data and accounts (idempotent). |
| `seed-summary` | Print record counts. |
| `create-demo-users` | Create or reconcile the demonstration accounts from `.env`. |
| `create-user --username U --role reviewer\|admin` | Create a user (password from `REGULENS_NEW_USER_PASSWORD` or a prompt). |
| `grant-cross-case --username U [--revoke]` | Grant or revoke the cross-case reviewer permission (audited). |
| `reuse-fixtures --load` | Add four fictional cross-case demonstration cases. |
| `reuse-fixtures --reset --confirm-reset` | Remove only those demonstration cases (development/test only). |
| `reuse-scan --application CODE` | Run a cross-case reuse scan for one application. |
| `reuse-eval [--no-ocr] --out DIR` | Run the A0/A1/A4 evaluation; writes `metrics.json`, `metrics.csv` and `summary.md`. |
| `capture-kit --out DIR` | Export printable sources and a manifest template for real photographed evaluation pairs. |
| `reset-data --confirm-reset` | **Delete all** institution, application and document data (development/test only). |

---

## Guided walkthrough

1. Sign in as `demo.reviewer`. **Overview** shows live queue counts, priority applications and backend status.
2. Open **Applications → REG-EoA-2026-0005** (a deliberately inconsistent fictional case; codes assume a fresh
   database). Under **Supporting documents** choose **Process all**, then **Details** on a document to see extracted
   fields with quoted evidence, page numbers and OCR confidence.
3. Run **Simulated issuer check**: the result shows its source-verification status with the `SIMULATED` source type.
4. Run **Preliminary scrutiny**. Open a finding to read its explanation, evidence and rule provenance; confirm or
   dismiss it with a reason. Download the **preliminary report** (PDF).
5. Raise an **evidence request**, upload the requested document linked to it, and mark the request fulfilled. The
   **Activity** panel and **Alerts** reflect each step.
6. For cross-case reuse, run `python -m app.cli reuse-fixtures --load` and
   `python -m app.cli grant-cross-case --username demo.reviewer`, sign in again, open the first fixture case and
   choose **Run cross-case scan → Open comparison**. The comparison shows both pages side by side, alignment and
   difference regions, field-level evidence, an evidence-referenced explanation and the reviewer decision panel.
7. Sign in as `demo.admin` to manage **Scrutiny Rules** and **Users**, review the **Audit Trail**, and run the
   evaluation under **Cross-case reuse**.

---

## Testing and quality

```powershell
cd backend;  .\.venv\Scripts\Activate.ps1; python -m pytest; cd ..
cd frontend; npm test; npm run typecheck; npm run build; npm audit; cd ..
```

Backend tests run against temporary databases and storage and never touch `data/`. Tests that require a real OCR
engine are skipped automatically when it is not installed.

### Browser smoke test

`frontend/e2e/smoke.mjs` drives the running application in Microsoft Edge: sign-in, scrutiny, finding actions,
upload and confirmed deletion, report download, permission denial, administration, and a layout sweep from 360 px to
1920 px. **It writes data**, so point it at a disposable database:

```powershell
# backend/ (venv active) — disposable instance on port 8030
$env:REGULENS_DATABASE_URL = "sqlite:///$env:TEMP/regulens-smoke.db"
$env:REGULENS_DOCUMENT_STORAGE_DIR = "$env:TEMP/regulens-smoke-docs"
$env:REGULENS_CORS_ORIGINS = "http://127.0.0.1:5195"
python -m app.cli seed
python -m uvicorn app.main:app --host 127.0.0.1 --port 8030

# frontend/
$env:VITE_API_BASE_URL = "http://127.0.0.1:8030/api/v1"; npx vite --port 5195 --strictPort --host 127.0.0.1

# frontend/ (third terminal)
$env:SMOKE_ALLOW_WRITES = "1"; $env:SMOKE_BASE_URL = "http://127.0.0.1:5195"; $env:SMOKE_API_URL = "http://127.0.0.1:8030/api/v1"
npm run smoke
```

The script refuses to run without `SMOKE_ALLOW_WRITES=1`.

---

## Evaluation

Cross-case reuse detection is measured on a deterministic, fully synthetic benchmark (63 fictional documents) with
separate development and held-out splits. Three arms are compared on identical labelled pairs: **A0** exact SHA-256,
**A1** perceptual hash only, and **A4** the full cascade. Only `MATCH_CONFIRMED_FOR_REVIEW` counts as a positive for
A4; inconclusive outcomes and altered-document pairs are reported separately.

Held-out results with local OCR (TP / FP / TN / FN):

| Split | A0 | A1 | A4 |
|---|---|---|---|
| heldout (15 pairs) | 1 / 0 / 8 / 6 | 3 / 2 / 6 / 4 | 7 / 0 / 8 / 0 |
| heldout2 (12 pairs) | 1 / 0 / 6 / 5 | 3 / 1 / 5 / 3 | 5 / 0 / 6 / 1 |
| heldout_alt (3 pairs) | 0 / 0 / 1 / 2 | 0 / 1 / 0 / 2 | 1 / 0 / 1 / 1 |

A4 produced no false positives on any split; its remaining misses are poor-quality scans, reported as
`INCONCLUSIVE` rather than confirmed. Altered certificates are surfaced as review candidates and never confirmed.
These figures come from a small synthetic benchmark and are not a claim of production accuracy. Full results,
split history and per-transformation breakdowns: [docs/evaluation/](docs/evaluation/) and
[docs/d9-acceptance.md](docs/d9-acceptance.md).

---

## Security and privacy

- Passwords are stored as salted scrypt hashes; sessions use opaque bearer tokens stored only as SHA-256 hashes.
- Sign-in lockout, server-side role checks on every endpoint, and request schemas that reject unknown fields.
- Documents are stored privately under server-generated keys and are reachable only through authenticated endpoints.
- Cross-case details require an explicit permission; ordinary reviewers receive alerts that never reveal the linked
  case. Every permitted and refused cross-case access is audited.
- The audit log is append-only at the application level and records actor, time, action and outcome — never
  document text, passwords or tokens.
- OCR and extracted text are treated as untrusted data and never executed or followed as instructions.
- All demonstration data is fictional. Do not load real institutional records into a development instance.

See [docs/security.md](docs/security.md).

---

## Limitations

- Scrutiny rules marked **demo-only** are prototype expectations and have not been verified against official AICTE
  sources.
- Issuer verification is **simulated**; no issuing authority is contacted.
- Field extraction is rule-based and covers explicitly labelled values in English; unusual layouts may be missed.
- Every reviewer can open every application; there is no per-application assignment.
- Reuse-detection accuracy has been measured on synthetic data only; real photographed documents have not yet been
  evaluated (`capture-kit` prepares that evaluation).
- SQLite and synchronous processing suit a single-site deployment; large volumes would need a server database and
  background workers.

---

## Repository layout

```
regulens-ai/
├── backend/                 FastAPI application
│   ├── app/                 api · core · db (Alembic migrations) · models · schemas · services
│   ├── tests/               pytest suite
│   ├── requirements.lock.txt
│   └── requirements-ocr.txt optional local OCR engine
├── frontend/                React + TypeScript application
│   ├── src/                 app · components · layouts · pages · services · types
│   ├── tests/               Vitest suite
│   └── e2e/                 browser smoke test
├── docs/                    architecture, API, data model, security, evaluation
├── data/                    local database and private document storage (git-ignored)
└── .env.example             documented configuration
```

---

## Documentation

| Topic | Document |
|---|---|
| Requirements | [docs/requirements.md](docs/requirements.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| API reference | [docs/api-contracts.md](docs/api-contracts.md) |
| Data model and migrations | [docs/data-model.md](docs/data-model.md) |
| Document processing and scrutiny rules | [docs/scrutiny-and-extraction.md](docs/scrutiny-and-extraction.md) |
| Reviewer workflow | [docs/review-workflow.md](docs/review-workflow.md) |
| Cross-case reuse detection | [docs/reuse-detection.md](docs/reuse-detection.md) |
| OCR, evidence fusion and explanations | [docs/ai-document-understanding.md](docs/ai-document-understanding.md) |
| Security, roles and audit | [docs/security.md](docs/security.md) |
| Design system | [docs/design-system.md](docs/design-system.md) |
| Acceptance checklist and status mapping | [docs/d9-acceptance.md](docs/d9-acceptance.md) |
| Implementation status | [docs/implementation-status.md](docs/implementation-status.md) |
