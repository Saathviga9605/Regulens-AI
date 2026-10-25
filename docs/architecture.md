# Architecture

## Overview

```
 Browser
   │  React SPA (Vite dev server :5173 / static build)
   │  src/services/apiClient.ts  ── fetch JSON ──┐
   ▼                                             ▼
 FastAPI (uvicorn :8000)  /api/v1/*
   middleware (outer → inner): CORS → request-id → upload size limit → routers
   routers (api/v1)  →  services  →  SQLAlchemy Session  →  SQLite file (data/regulens.db)
                                 └→ DocumentStorage    →  private files (data/documents/)
   error handlers (core/errors.py) wrap every failure in a uniform JSON body
```

The frontend never accesses the database or filesystem; the backend is the only data gateway. Stored documents
are reachable only through `GET /api/v1/documents/{id}/content`; no static file mount exists.

## Backend (`backend/app`)

| Package | Responsibility |
|---------|----------------|
| `main.py` | `create_app(settings)` factory: builds engine/session factory, middleware, CORS, error handlers, routers; lifespan runs `init_db`. Module-level `app` for uvicorn. |
| `core/config.py` | Single `Settings` class (pydantic-settings, `REGULENS_` prefix, reads repo-root `.env`). Resolves relative SQLite paths against the repo root. |
| `core/logging.py` | JSON-lines logging to stdout. Stack traces are logged server-side only. |
| `core/errors.py` | Handlers for HTTP, validation and unexpected exceptions → `{"error": {...}}`. |
| `db/` | `base.py` (DeclarativeBase), `session.py` (engine, session factory, per-request session scope), `init_db.py`. |
| `api/deps.py` | FastAPI dependencies: `get_app_settings`, `get_db`. |
| `api/v1/` | Routers. Thin: call services, return schemas. |
| `core/limits.py` | `UploadSizeLimitMiddleware`: 413 from Content-Length or while streaming, before the body is spooled. |
| `services/` | Logic: health, system_info, institutions, applications, workflow (status rules), codes (ID generation), seed, documents (intake/duplicates/deletion), storage (private file layout). |
| `schemas/` | Pydantic request/response models. |
| `models/` | ORM models: Institution, Application, ApplicationProgramme, IdSequence, Document; enums. |

Settings and engine are stored on `app.state`, so tests build fully isolated apps via `create_app(test_settings)`.

## Request flow: health check

1. Dashboard mounts → `BackendHealthProvider` calls `apiClient.getHealth()`.
2. `GET {VITE_API_BASE_URL}/health` → request-id middleware → CORS → `system.health`.
3. `get_db` opens a session; `check_database` executes `SELECT 1`.
4. Response: `status: ok` if the query succeeds, otherwise `degraded` with a safe detail message.
5. Frontend derives `connected` / `degraded`; network/HTTP/invalid-JSON errors → `disconnected`. Retry repeats step 1.

If the database is unusable at startup, `init_db` failure is logged and the app still starts so that `/health`
can report `degraded` truthfully.

## Request flow: document upload

1. `DocumentsPanel` → `apiClient.uploadDocument` posts `multipart/form-data` (`file`, `category`, `description?`).
2. `UploadSizeLimitMiddleware` rejects bodies over the limit (Content-Length or streamed byte count) with 413.
3. Route checks the application exists and accepts documents, sanitises the filename (base name only), checks the
   declared content type.
4. `receive_upload` streams 64 KiB chunks to `<storage>/.incoming/<uuid>.part`, counting bytes and computing SHA-256;
   then checks the `%PDF-` signature and `%%EOF` marker. Any failure deletes the temp file.
5. `store_document` inserts the row (duplicate lookup by SHA-256 within the application), moves the temp file to
   `<storage>/<key[:2]>/<key>.pdf`, then commits. A commit failure deletes the moved file; a storage failure records an
   `intake_failed` row with no content.
6. Response is built from the committed row.

Deletion isolates the file in `<storage>/.trash/`, deletes the row (promoting/relinking duplicates), commits, then
discards the isolated file; on commit failure the file is moved back.

## Document intelligence and scrutiny (Deliverable 4)

```
stored PDF ──► pdf_text (PyMuPDF; Tesseract subprocess if available)
             ──► classification (weighted keyword/heading signals)
             ──► extraction (label regex, evidence quote grounded in page text)
             ──► document_processing / document_pages / extracted_fields   (cached by sha256 + pipeline version)

application + institution record + processed documents + latest simulated issuer checks
             ──► scrutiny engine: enabled rules (validated JSON parameters) → rule_evaluations
                                  anomaly detectors → findings (kind = anomaly_indicator)
             ──► scrutiny_runs (rule snapshot, summary, warnings) — history kept per application

issuer_verification.IssuerVerificationAdapter ◄── MockIssuerAdapter (synthetic reference records only; no network)
```

| Module | Responsibility |
|--------|----------------|
| `services/pdf_text.py` | Page extraction, OCR heuristic and bounds, safe failure codes |
| `services/classification.py` | Explainable classifier and documented confidence |
| `services/extraction.py`, `services/normalize.py` | Field specs, grounding, date/area/name/identifier normalisation |
| `services/processing.py` | Orchestration, caching, persistence; never changes the selected category |
| `services/rule_catalog.py` | Rule types, parameter schemas, default (demo-only / integrity) rules |
| `services/scrutiny.py` | Evaluators per rule type, anomaly detectors, run execution and queries |
| `services/issuer_verification.py` | Adapter protocol and the mock synthetic adapter |
| `services/demo_documents.py` | Fictional demo PDFs and synthetic reference records for the seed |
| `api/v1/scrutiny.py` | Processing, verification, rules, runs and findings endpoints |

Processing and runs execute synchronously in the request (threadpool), bounded by page limits and OCR timeouts.
A background worker would be the next step if documents grow large. See
[scrutiny-and-extraction.md](scrutiny-and-extraction.md) for heuristics, rules and limitations.

## Frontend (`frontend/src`)

| Dir | Responsibility |
|-----|----------------|
| `app/` | `App.tsx` (routes, wrapped in `ToastProvider`), `navigation.ts` (`NAV_GROUPS`, `TRUST_NOTICE`), `AuthContext`, `BackendHealthContext.tsx` (shared health state + refresh), `labels.ts`. |
| `layouts/` | `AppLayout` — sticky header (wordmark, environment badge, alerts count, account menu), trust-notice bar, grouped sidebar, mobile drawer, skip link, `<main>` outlet. |
| `pages/` | Login, Overview (`DashboardPage`), review queue, applications (list/create/workspace), institutions (list/create/detail), alerts, scrutiny rules, users, audit trail, Help & About, not found. |
| `components/` | `ConnectionIndicator`, `SystemStatusPanel`, `ApplicationForm`, `InstitutionForm`, `DocumentsPanel` (inventory, upload, processing status, process all, details, open/download, confirmed delete), `DocumentAnalysis` (classification, fields with evidence, page text, simulated issuer checks), `ScrutinyPanel` (runs, history, summary, findings, finding detail, human review), `ui.tsx` design-system primitives (see [design-system.md](design-system.md)), `Toast.tsx`, `BrandMark.tsx`. |
| `services/` | `apiClient.ts` — typed fetch wrapper with timeout, error normalisation (`ApiError`), response shape check. |
| `types/` | API types mirroring backend schemas, `ConnectionState` union. |

## Configuration

One `.env` at the repo root. Backend reads `REGULENS_*`; Vite reads `VITE_*` (its `envDir` is `..`).
See `.env.example`. Production mode disables `/docs` and rejects wildcard CORS.

## Future module boundaries

Each future domain gets its own `models/<x>.py`, `schemas/<x>.py`, `services/<x>/`, `api/v1/<x>.py` and a frontend
page + typed client functions:

- **applications** — application + institution records (implemented, D2).
- **documents** — PDF intake, private storage, exact-duplicate detection (D3); processing, OCR, extraction (D4).
- **scrutiny** — rules, runs, findings, anomaly indicators, simulated issuer checks (D4).
- **regulatory sources** — verified official source documents that rules can cite (planned; current rules are demo-only or integrity checks).
- **review / reports / audit** — reviewer queue, human decisions, preliminary reports, append-only audit log.
- **auth** — users, roles, session/token handling.

Long-running work (OCR, extraction) is expected to run as in-process background tasks first; a separate worker is
only introduced if needed.

## Reviewer workspace (Deliverable 5)

```
browser ── Bearer token ──► router (get_current_actor → contextvars actor/request id; require_admin on admin routes)
                              ├─ services/review.py   review actions, evidence requests  ─┐
                              ├─ services/queue.py    queue summary from latest runs      │ same transaction:
                              ├─ services/report.py   PDF (PyMuPDF Story)                 ├─ audit.record(...)
                              ├─ services/copilot.py  intent → retrieval → templates      │  alerts.raise_alert(...)
                              └─ existing services (documents, processing, scrutiny, rules)┘
```
Auth: `services/auth.py`, `core/security.py`, `api/deps.py`. Frontend: `AuthContext` + `guards` (UI only; the
server enforces roles), `ReviewQueuePage`, `ReviewActions`, `EvidenceRequestsPanel`, `CopilotPanel`, `ActivityLog`,
`AlertsPage`, `AuditTrailPage`, `UsersPage`; the API client attaches the token and fetches documents/reports as blobs.

## Cross-case reuse (Deliverable 7)

`services/reuse_engine.py` (pure cascade + decision), `reuse_visual.py` (rendering, pHash, ORB/RANSAC, residual
map; OpenCV + NumPy), `reuse.py` (scans, persistence, restricted views, dispositions, evaluation storage),
`reuse_dataset.py` / `reuse_eval.py` (synthetic fixtures, A0/A1/A4), `reuse_fixtures.py` (demo cases).
API in `api/v1/reuse.py` (open router, permission-guarded `restricted_router`, `evaluation_router`).
Frontend: `components/CrossCasePanel.tsx` (workspace section), `pages/CasePairPage.tsx` (comparison),
`pages/CrossCasePage.tsx` (pair list + evaluation), Users page permission toggle. Scans are synchronous with a
per-application running-scan guard; no queue or broker. See [reuse-detection.md](reuse-detection.md).

## Local OCR, evidence fusion and explanations (Deliverable 8)

`services/ocr.py` (local OCR providers: Tesseract TSV and RapidOCR/ONNX Runtime, explicit selection, capability
report), `pdf_text.py` (text layer first, OCR fallback with bounded rotation retries, line coordinates for every
page), `extraction.py` (`label_regex_v2`, evidence boxes and OCR scores), `reuse_engine.py` (`reuse_cascade_v3`: region
mapping, `fuse`, `explain`), `reuse_visual.py` (`phash_dct_v2` photo rectification). UI: capability strip and stages
in the cross-case panel; explanation, fusion and field boxes on the comparison page; OCR details in document
analysis. See [ai-document-understanding.md](ai-document-understanding.md).
