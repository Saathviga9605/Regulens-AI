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

## Frontend (`frontend/src`)

| Dir | Responsibility |
|-----|----------------|
| `app/` | `App.tsx` (routes), `navigation.ts` (module definitions), `BackendHealthContext.tsx` (shared health state + refresh). |
| `layouts/` | `AppLayout` — responsive navy sidebar, skip link, connection indicator, `<main>` outlet. |
| `pages/` | Dashboard, applications (list/create/detail), institutions (list/create/detail), `ModulePlaceholderPage`, `NotFoundPage`. |
| `components/` | `ConnectionIndicator`, `SystemStatusPanel`, `ApplicationForm`, `InstitutionForm`, `DocumentsPanel` (inventory, upload, details, open/download, confirmed delete), `ui.tsx` primitives. |
| `services/` | `apiClient.ts` — typed fetch wrapper with timeout, error normalisation (`ApiError`), response shape check. |
| `types/` | API types mirroring backend schemas, `ConnectionState` union. |

## Configuration

One `.env` at the repo root. Backend reads `REGULENS_*`; Vite reads `VITE_*` (its `envDir` is `..`).
See `.env.example`. Production mode disables `/docs` and rejects wildcard CORS.

## Future module boundaries

Each future domain gets its own `models/<x>.py`, `schemas/<x>.py`, `services/<x>/`, `api/v1/<x>.py` and a frontend
page + typed client functions:

- **applications** — application + institution records (implemented, D2).
- **documents** — PDF intake, private storage, exact-duplicate detection (implemented, D3); OCR pipeline next.
- **extraction** — structured fields with evidence (document, page, span, confidence).
- **rules** — versioned rule definitions with regulatory provenance; rule engine producing findings.
- **consistency / anomalies** — cross-document checks, anomaly flags (non-conclusive).
- **verification** — simulated issuer verification adapters behind an interface.
- **review / reports / audit** — reviewer queue, human decisions, preliminary reports, append-only audit log.
- **auth** — users, roles, session/token handling.

Long-running work (OCR, extraction) is expected to run as in-process background tasks first; a separate worker is
only introduced if needed.
