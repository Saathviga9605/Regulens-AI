# Architecture

## Overview

```
 Browser
   │  React SPA (Vite dev server :5173 / static build)
   │  src/services/apiClient.ts  ── fetch JSON ──┐
   ▼                                             ▼
 FastAPI (uvicorn :8000)  /api/v1/*
   middleware: request-id → CORS → routers
   routers (api/v1)  →  services  →  SQLAlchemy Session  →  SQLite file (data/regulens.db)
   error handlers (core/errors.py) wrap every failure in a uniform JSON body
```

The frontend never accesses the database or filesystem; the backend is the only data gateway.

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
| `services/` | Logic: health, system_info, institutions, applications, workflow (status rules), codes (ID generation), seed. |
| `schemas/` | Pydantic response models. |
| `models/` | ORM models: Institution, Application, ApplicationProgramme, IdSequence; enums. |

Settings and engine are stored on `app.state`, so tests build fully isolated apps via `create_app(test_settings)`.

## Request flow: health check

1. Dashboard mounts → `BackendHealthProvider` calls `apiClient.getHealth()`.
2. `GET {VITE_API_BASE_URL}/health` → request-id middleware → CORS → `system.health`.
3. `get_db` opens a session; `check_database` executes `SELECT 1`.
4. Response: `status: ok` if the query succeeds, otherwise `degraded` with a safe detail message.
5. Frontend derives `connected` / `degraded`; network/HTTP/invalid-JSON errors → `disconnected`. Retry repeats step 1.

If the database is unusable at startup, `init_db` failure is logged and the app still starts so that `/health`
can report `degraded` truthfully.

## Frontend (`frontend/src`)

| Dir | Responsibility |
|-----|----------------|
| `app/` | `App.tsx` (routes), `navigation.ts` (module definitions), `BackendHealthContext.tsx` (shared health state + refresh). |
| `layouts/` | `AppLayout` — responsive navy sidebar, skip link, connection indicator, `<main>` outlet. |
| `pages/` | `DashboardPage`, `ModulePlaceholderPage` (planned modules), `NotFoundPage`. |
| `components/` | `ConnectionIndicator`, `SystemStatusPanel`. |
| `services/` | `apiClient.ts` — typed fetch wrapper with timeout, error normalisation (`ApiError`), response shape check. |
| `types/` | API types mirroring backend schemas, `ConnectionState` union. |

## Configuration

One `.env` at the repo root. Backend reads `REGULENS_*`; Vite reads `VITE_*` (its `envDir` is `..`).
See `.env.example`. Production mode disables `/docs` and rejects wildcard CORS.

## Future module boundaries

Each future domain gets its own `models/<x>.py`, `schemas/<x>.py`, `services/<x>/`, `api/v1/<x>.py` and a frontend
page + typed client functions:

- **applications** — application + institution records.
- **documents** — upload, storage (local `data/uploads/`, git-ignored), OCR pipeline.
- **extraction** — structured fields with evidence (document, page, span, confidence).
- **rules** — versioned rule definitions with regulatory provenance; rule engine producing findings.
- **consistency / anomalies** — cross-document checks, anomaly flags (non-conclusive).
- **verification** — simulated issuer verification adapters behind an interface.
- **review / reports / audit** — reviewer queue, human decisions, preliminary reports, append-only audit log.
- **auth** — users, roles, session/token handling.

Long-running work (OCR, extraction) is expected to run as in-process background tasks first; a separate worker is
only introduced if needed.
