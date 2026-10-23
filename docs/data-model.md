# Data Model

## Current state (Deliverable 1)

**No business tables exist.** The database layer is in place and verified, ready for models.

### Database

- SQLite via SQLAlchemy 2.0. URL from `REGULENS_DATABASE_URL` (default `sqlite:///data/regulens.db`,
  resolved against the repo root). The parent directory is created automatically. Files are git-ignored.
- `PRAGMA foreign_keys=ON` is set on every connection.

### Initialisation

`app/db/init_db.py:init_db(engine)` runs in the FastAPI lifespan:

1. `Base.metadata.create_all()` for all models imported in `app/models/__init__.py` (currently none).
2. `SELECT 1` to confirm connectivity.

Failure is logged and the app keeps running so `/health` reports `degraded`. Alembic migrations will replace
`create_all` before any existing table needs changing.

### Sessions

- `build_session_factory` → `sessionmaker(autoflush=False, expire_on_commit=False)`.
- `api/deps.get_db` yields one session per request; rolls back on exception, always closes.
- Engine and session factory live on `app.state`, so each test app has its own temporary database.

## Planned entities (not implemented)

| Entity | Purpose | Key relationships |
|--------|---------|-------------------|
| Institution | Synthetic institutional record (name, AICTE id, address, type) | has many Applications |
| Application | EoA application for an academic year | belongs to Institution; has Documents, Findings, Decisions |
| Document | Uploaded PDF (filename, hash, type, storage path, page count) | belongs to Application; has Pages |
| DocumentPage | OCR text per page | belongs to Document |
| ExtractedField | Structured value with evidence (page, span/bbox, method, confidence) | belongs to Document |
| RegulatorySource | Handbook/notification (title, edition, year, URL) | has many Rules |
| Rule | Versioned validation rule (clause ref, parameters, effective dates) | belongs to RegulatorySource |
| Finding | Rule/consistency/anomaly result (severity, message, status) | links Application, Rule, ExtractedField evidence |
| VerificationRequest | Simulated issuer verification (issuer, status, response) | belongs to Document |
| ReviewDecision | Human reviewer decision with rationale | belongs to Application, User |
| AuditEvent | Append-only log (actor, action, entity, timestamp, payload) | references any entity |
| User | Reviewer/admin account with role | has Decisions, AuditEvents |

These are design intentions and will be refined when each deliverable is built.
