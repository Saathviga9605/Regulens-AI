# CLAUDE.md — ReguLens AI

Instructions for every Claude Code session in this repository. Read before changing code.

## Purpose

ReguLens AI is an **evidence-first regulatory scrutiny assistant** for AICTE Extension of Approval (EoA)
applications from existing technical institutions (Smart India Hackathon prototype). It helps human reviewers;
it **never** approves or rejects an application, declares fraud, or treats an anomaly as proof of misconduct.
The prototype uses synthetic institutional data and simulated external verification — never assume access to
private AICTE systems or real government APIs.

## Architecture

```
frontend/ (React + Vite + TS)  --HTTP JSON-->  backend/ (FastAPI)  --SQLAlchemy-->  SQLite (data/regulens.db)
```

- Backend: `app/main.py` (`create_app` factory) → `api/v1/*` routers → `services/*` (logic) → `db/*` (engine/session).
  `core/` holds config, logging, error handlers. `schemas/` holds Pydantic response models. `models/` holds ORM models.
- Frontend: `src/services/apiClient.ts` is the **only** place that calls the backend. `src/app/` holds routing,
  navigation config and app-wide providers; `layouts/`, `pages/`, `components/`, `types/` as named.
- Full detail: `docs/architecture.md`. Current state: `docs/implementation-status.md`.

## Stack

Python 3.11+ (verified 3.13), FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.0, SQLite, Pytest + HTTPX.
React 18, Vite 6, TypeScript (strict), Tailwind CSS v4, React Router 7, lucide-react, Vitest + React Testing Library.

## Commands (Windows PowerShell, from repo root)

```powershell
# backend
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.lock.txt; pip install -e ".[dev]"
python -m app.cli migrate; python -m app.cli seed  # schema + synthetic data
python -m pytest                                   # tests
python -m uvicorn app.main:app --reload --port 8000  # run

# frontend
cd frontend; npm ci
npm test; npm run typecheck; npm run build; npm run dev
```

## Coding conventions

- Backend: type hints everywhere; routers stay thin (validate → call service → return schema). Business logic
  lives in `services/`, DB access via injected `Session` (`api/deps.get_db`). Never read env vars outside
  `core/config.py`; get settings from `request.app.state.settings` / `get_app_settings`.
- Frontend: strict TS, no `any`. Shared API types in `src/types/api.ts` mirror backend schemas — update both.
  Enum display labels live in `src/app/labels.ts`. Components never call `fetch` directly: add methods to
  `services/apiClient.ts` and load data with `useApiQuery`. Reuse `components/ui.tsx` primitives (fields,
  states, table styles). Never render hardcoded records; tests mock `fetch` with `tests/helpers.tsx:mockApi`. Tailwind utility classes; slate/navy + restrained blue palette.
- Keep new modules out of the tree until they have real code. No empty placeholders claiming functionality.

## API conventions

- All routes under `/api/v1`. Responses are Pydantic models (`response_model=`).
- Errors use one shape: `{"error": {"code", "message", "request_id", "details?"}}` (see `core/errors.py`).
- Never return stack traces, exception text, filesystem paths, DB URLs or secrets to clients.
- Health must reflect real dependency checks; never hardcode "ok".

## Database conventions

- SQLAlchemy 2.0 typed ORM (`Mapped[...]`), models inherit `app.db.base.Base` and are imported in `app/models/__init__.py`.
- One session per request via `get_db`; services call `session.commit()`; `session_scope` rolls back on error.
- **Schema changes go through Alembic** (`app/db/migrations`). Autogenerate, review, replace app types with `sa.*`
  in the migration, never edit an applied revision. `init_db` / `python -m app.cli migrate` run `upgrade head`.
- Enums: `StrEnum` in `app/models/enums.py`, columns via `app.db.types.str_enum`. Timestamps: `UTCDateTime` + `utcnow()`.
- Human-readable IDs come from `app/services/codes.py` (atomic counters). Never derive IDs by counting rows.
- Expose codes (`INST-…`, `REG-EoA-…`) in URLs/responses, never internal UUIDs.
- Seed data is synthetic, keyed by `seed_key`, and never overwrites records. Destructive commands require an explicit
  flag and are never run at startup or against the developer database in tests.
- Database files live in `data/` and are git-ignored. Tests must use temporary databases (see `tests/conftest.py`).

## Request/response schema conventions

- Request bodies inherit `StrictInputModel` (unknown fields → 422, prevents mass assignment); PATCH bodies inherit
  `PartialUpdateModel` (no explicit nulls). Separate Create / Update / Read schemas.
- Expected domain errors raise `AppError` / `NotFoundError` / `ConflictError` (`core/errors.py`) with client-safe messages;
  field-specific business errors use 422 with `details[].loc` so the frontend can show them on the field.
- Lists return `Page[T]` with `get_pagination` (max page size 100) and a stable `order_by`; eager-load relations.
- Application status changes only through `services/workflow.py`. Statuses are internal, never AICTE decisions.
- Authorization (future) is added as a router-level dependency in `api/v1/router.py`.

## Security requirements

- No secrets in code or git. `.env` is ignored; document new settings in `.env.example`.
- CORS: explicit origin list only; wildcard rejected in production. `/docs` disabled in production.
- Validate all input with Pydantic. Treat uploaded files (future) as untrusted: size/type limits, no path traversal,
  store outside web root.
- The frontend never touches the database or filesystem directly.

## Evidence-grounding requirements (future extraction features)

- Every extracted value must carry provenance: document id, page number, and source text span/bounding box,
  plus extraction method and confidence.
- Values without evidence must be shown as "not found", never inferred or fabricated.
- LLM output must be validated against the source text; unsupported claims are discarded or flagged.

## Regulatory-rule provenance

- Every validation rule records: source document (e.g. AICTE Approval Process Handbook edition/year), clause or
  section reference, effective dates, and version. Rules are data/config, not hardcoded logic.
- Every finding links to the rule (with provenance) and to the evidence that triggered it.

## Human-review safeguards

- The system produces *preliminary* findings and reports only. Wording: "requires review", "inconsistency
  detected" — never "fraud", "rejected", "approved".
- Final decisions are recorded by a human reviewer, with reviewer identity and rationale in the audit trail.
- Anomaly scores are prompts for attention, never conclusions.

## Definition of done for any feature

A feature is complete only when its automated tests have been **run and passed**. Update
`docs/implementation-status.md` honestly (Implemented and tested / Implemented but not fully tested / Planned /
Blocked), and update `docs/api-contracts.md` / `docs/data-model.md` when contracts or schema change.
