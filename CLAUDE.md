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
  Components never call `fetch` directly. Tailwind utility classes; slate/navy + restrained blue palette.
- Keep new modules out of the tree until they have real code. No empty placeholders claiming functionality.

## API conventions

- All routes under `/api/v1`. Responses are Pydantic models (`response_model=`).
- Errors use one shape: `{"error": {"code", "message", "request_id", "details?"}}` (see `core/errors.py`).
- Never return stack traces, exception text, filesystem paths, DB URLs or secrets to clients.
- Health must reflect real dependency checks; never hardcode "ok".

## Database conventions

- SQLAlchemy 2.0 typed ORM (`Mapped[...]`), models inherit `app.db.base.Base` and are imported in `app/models/__init__.py`.
- One session per request via `get_db`; rollback on error, always close.
- `init_db` uses `create_all` for now. Introduce Alembic before the first schema change to an existing table.
- Database files live in `data/` and are git-ignored. Tests must use temporary databases (see `tests/conftest.py`).

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
