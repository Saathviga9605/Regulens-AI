# Data Model

SQLite via SQLAlchemy 2.0 (typed ORM). URL from `REGULENS_DATABASE_URL` (default `sqlite:///data/regulens.db`,
relative to the repo root; directory auto-created; git-ignored). `PRAGMA foreign_keys=ON` on every connection;
30 s lock wait timeout for concurrent writers.

## Schema management (Alembic)

- Migrations live in `backend/app/db/migrations/versions/`. Revision `0001` creates the four tables below.
- `init_db` (FastAPI startup) and `python -m app.cli migrate` run `alembic upgrade head` on the configured database.
  This works on fresh databases and on existing ones (e.g. a Deliverable 1 database): only missing structures are
  added and existing tables/rows are untouched. `create_all` is no longer used.
- If a migration fails at startup, the error is logged and `/health` reports `degraded`.
- New schema change: edit models, then from `backend/`:
  `alembic revision --autogenerate -m "describe change"` → review the file (replace app-specific types with plain
  `sa.*` types) → `python -m app.cli migrate`. Never edit an applied migration.
- Enums are stored as `VARCHAR` + `CHECK` constraints (portable; no native DB enum).
- Timestamps: stored as naive UTC (SQLite lacks time zones) via `UTCDateTime`; naive input is refused; values are
  always returned timezone-aware UTC.

## Tables

### institutions
| Column | Type | Constraints / notes |
|--------|------|---------------------|
| id | VARCHAR(36) | PK, UUID4, internal only |
| institution_code | VARCHAR(20) | UNIQUE, NOT NULL, generated `INST-00001` |
| name | VARCHAR(200) | NOT NULL |
| name_normalized | VARCHAR(200) | NOT NULL, INDEX; case-folded, whitespace-collapsed (search/sort) |
| institution_type | VARCHAR(40) | CHECK enum |
| state, district | VARCHAR(80) | NOT NULL; composite INDEX (state, district) |
| address | TEXT | NOT NULL |
| trust_name | VARCHAR(200) | NOT NULL — trust / sponsoring body |
| property_identifier | VARCHAR(100) | NOT NULL — property / survey number |
| status | VARCHAR(40) | CHECK `active`/`inactive`, default `active` |
| seed_key | VARCHAR(50) | UNIQUE, NULL for user records |
| created_at, updated_at | DATETIME (UTC) | NOT NULL |

### applications
| Column | Type | Constraints / notes |
|--------|------|---------------------|
| id | VARCHAR(36) | PK, UUID4, internal only |
| application_code | VARCHAR(30) | UNIQUE, generated `REG-EoA-2026-0001` |
| institution_id | VARCHAR(36) | FK → institutions.id `ON DELETE RESTRICT`, INDEX |
| category | VARCHAR(40) | CHECK; only `extension_of_approval` |
| academic_year | VARCHAR(7) | INDEX; `YYYY-YY` validated in the API layer |
| application_type | VARCHAR(40) | CHECK enum, INDEX |
| status | VARCHAR(40) | CHECK enum, INDEX, default `draft` |
| submitted_at | DATETIME (UTC) | NULL; internal "marked ready" time (not an AICTE submission) |
| status_changed_at | DATETIME (UTC) | NOT NULL |
| institution_snapshot | JSON | NULL; institution details captured when marked ready |
| seed_key | VARCHAR(50) | UNIQUE, NULL for user records |
| created_at, updated_at | DATETIME (UTC) | NOT NULL; INDEX (created_at, application_code) for list order |

### application_programmes
| Column | Type | Constraints / notes |
|--------|------|---------------------|
| id | INTEGER | PK |
| application_id | VARCHAR(36) | FK → applications.id `ON DELETE CASCADE`, INDEX |
| position | INTEGER | display order |
| programme_level | VARCHAR(40) | CHECK `diploma`/`undergraduate`/`postgraduate` |
| course_name | VARCHAR(150) | |
| shift | VARCHAR(40) | CHECK `first`/`second` |
| existing_intake, proposed_intake | INTEGER | CHECK 0–600 |
| | | UNIQUE (application_id, programme_level, course_name, shift) |

### id_sequences
| Column | Type | Notes |
|--------|------|-------|
| name | VARCHAR(50) PK | `institution`, `application:2026`, … |
| last_value | INTEGER | last issued number |

## Relationships

Institution 1 — * Application 1 — * ApplicationProgramme. Institutions cannot be deleted while applications
reference them (RESTRICT); no delete endpoint exists.

## Identifier generation (concurrency-safe)

Inside the creating transaction: `INSERT … ON CONFLICT DO NOTHING` the counter row, then a single atomic
`UPDATE id_sequences SET last_value = last_value + 1 … RETURNING last_value`. The database write lock serialises
concurrent creators; the counter commits or rolls back together with the new record; UNIQUE constraints on the
code columns are a final guard. Existing rows are never counted. Tested with 24 concurrent creations (8 threads).
Note: the upsert uses the SQLite dialect; a PostgreSQL move needs the equivalent `postgresql.insert`.

## Application workflow

Internal ReguLens statuses — **none is an AICTE decision**:

| Status | Meaning | Editable | Allowed next |
|--------|---------|----------|--------------|
| `draft` | Being prepared in ReguLens | Yes | `ready_for_preliminary_scrutiny` |
| `ready_for_preliminary_scrutiny` | Details frozen for internal scrutiny. Prototype step: document intake/validation do not exist yet, so this does not prove required documents are present. | No | `draft` (correction path), `under_preliminary_scrutiny` |
| `under_preliminary_scrutiny` | Internal scrutiny in progress | No | `awaiting_additional_evidence`, `preliminary_scrutiny_completed` |
| `awaiting_additional_evidence` | Scrutiny paused pending evidence | No | `under_preliminary_scrutiny` |
| `preliminary_scrutiny_completed` | Internal scrutiny finished (terminal) | No | — |

Defined in `backend/app/services/workflow.py`. Side effects:
- → `ready_for_preliminary_scrutiny`: sets `submitted_at`, captures `institution_snapshot`, requires an active institution.
- → `draft`: clears `submitted_at` and `institution_snapshot`; editing is possible again.

## Business rules

1. Only `draft` applications can be edited (409 `application_frozen` otherwise). The only correction path is
   returning a `ready_for_preliminary_scrutiny` application to `draft`, before scrutiny starts.
2. An application must reference an existing, active institution.
3. IDs, codes, status and timestamps are server-controlled; request schemas reject them.
4. Status changes only via `POST /applications/{code}/status`, validated against the table above.
5. Institution edits update the live institution record but never rewrite a frozen application's
   `institution_snapshot`.
6. Academic year (`YYYY-YY`, consecutive) and intake (integer 0–600) rules are enforced by the API schema;
   programme/type consistency rules are enforced by the service (see api-contracts.md).
7. Updates validate the full merged result before mutating; each request is one transaction that rolls back on error.

## Synthetic seed

`app/services/seed.py`: 8 fictional institutions (8 states) and 12 applications (all 5 types, 3 academic years,
statuses reached through the real workflow service). Seed rows carry `seed_key`; reseeding skips existing keys and
never updates or deletes any row. `reset-data` deletes all institution/application data and requires
`--confirm-reset` and a `development`/`test` environment; it never runs automatically.

## Planned entities (not implemented)

Document, DocumentPage, ExtractedField (with page-level evidence), RegulatorySource, Rule (versioned, with
provenance), Finding, VerificationRequest, ReviewDecision, AuditEvent, User. These will reference `applications.id`
and `institutions.id`.
