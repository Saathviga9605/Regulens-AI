# Data Model

SQLite via SQLAlchemy 2.0 (typed ORM). URL from `REGULENS_DATABASE_URL` (default `sqlite:///data/regulens.db`,
relative to the repo root; directory auto-created; git-ignored). `PRAGMA foreign_keys=ON` on every connection;
30 s lock wait timeout for concurrent writers.

## Schema management (Alembic)

- Migrations live in `backend/app/db/migrations/versions/`. Revision `0001` creates institutions, applications, application_programmes and id_sequences; `0002` adds
  documents; `0003` adds processing, scrutiny and simulated-verification tables plus `documents.seed_key` (all additive:
  plain ADD COLUMN + new tables, no rebuild of existing tables; existing rows untouched).
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

### documents (migration `0002`)
| Column | Type | Constraints / notes |
|--------|------|---------------------|
| id | VARCHAR(36) | PK, UUID4 (public opaque id) |
| application_id | VARCHAR(36) | FK → applications.id `ON DELETE RESTRICT` |
| original_filename | VARCHAR(255) | sanitised base name; display only, never a path |
| storage_key | VARCHAR(32) | UNIQUE, server-generated hex; NULL only for `intake_failed` |
| category | VARCHAR(40) | CHECK enum (10 prototype categories after migration `0006`; includes Building License and Form D) |
| mime_type | VARCHAR(100) | detected from content (`application/pdf`) |
| size_bytes | BIGINT | CHECK ≥ 0 |
| sha256 | VARCHAR(64) | CHECK length 64, INDEX |
| uploaded_at | DATETIME (UTC) | |
| status | VARCHAR(40) | CHECK `uploaded` / `duplicate_detected` / `intake_failed` |
| duplicate_of_id | VARCHAR(36) | FK → documents.id `ON DELETE SET NULL`, INDEX; CHECK ≠ id |
| description | VARCHAR(500) | optional |
| created_at, updated_at | DATETIME (UTC) | |
| | | INDEX (application_id, uploaded_at), INDEX (application_id, sha256) |

`documents.seed_key` (migration `0003`, unique index) marks synthetic demo documents.

### Processing tables (migration `0003`)
| Table | Key columns | Notes |
|-------|-------------|-------|
| document_processing | id, document_id (FK CASCADE, UNIQUE), sha256 (INDEX), pipeline_version, status, failure_code/reason, page_count, pages_processed, ocr_available, warnings JSON, predicted_category, classification_score/confidence/signals/alternatives, reused_from_cache, pdf_properties JSON, started_at, finished_at | Latest result per document |
| document_pages | id, processing_id (FK CASCADE), page_number (1-based), method, status, text, char_count, warnings | UNIQUE (processing_id, page_number) |
| extracted_fields | id (UUID), processing_id (FK CASCADE), document_id (FK CASCADE), position, field_name, raw_value, normalized_value JSON, page_number, evidence_quote, method, confidence, status, warnings, candidates | INDEX (document_id, field_name) |

### Scrutiny tables (migration `0003`)
| Table | Key columns | Notes |
|-------|-------------|-------|
| scrutiny_rules | rule_id (PK), title, description, rule_type, parameters JSON, severity, enabled, source, source_reference, source_verification_status, is_demo_only, provenance, registry_managed, retired, effective_from, effective_to, version, timestamps | Migration `0005`; configuration kept by reset; managed rules permit only audited enabled-state changes |
| scrutiny_runs | id, application_id (FK RESTRICT), run_number, status, nullable scrutiny_date, scrutiny_date_source, rule_set_version, rule_snapshot JSON, documents_considered JSON, warnings, summary JSON, failure_reason, started_at, finished_at | Migration `0005`; UNIQUE (application_id, run_number); history is never deleted by reruns |
| rule_evaluations | id, run_id (FK CASCADE), position, rule_id, rule_version, subject_key, outcome, severity, explanation, document_ids/field_ids/evidence/compared_values JSON, missing_evidence, human_review_recommended | UNIQUE (run_id, rule_id, subject_key) |
| findings | id, application_id (FK RESTRICT), run_id (FK CASCADE), evaluation_id (FK CASCADE, nullable), finding_key, kind, finding_type, title, severity, outcome, explanation, uncertainty, rule_id/version or detector, evidence JSON, review_status, review_note, reviewed_at, created_at | UNIQUE (run_id, finding_key) — stable keys across runs |
| issuer_reference_records | id, reference_code (UNIQUE), document_category, issuing_authority, certificate_number(_normalized INDEX), institution_name, issue_date, valid_until, availability, seed_key | **Synthetic only** |
| verification_attempts | id, application_id (FK RESTRICT), document_id (FK SET NULL), document_filename, adapter, method, simulated, outcome, explanation, fields_compared JSON, reference_code, created_at | |

The reference date defaults to the application's internal `submitted_at` (marked-ready) date, not a verified
government submission date. An operator override is labelled; when neither is available the date remains null.
The system clock is not a fallback. Rule snapshots include evaluator version, provenance, and effective dates.

Evidence in evaluations/findings is stored as JSON snapshots (document id, filename, page, quote, value) rather than
foreign keys, so run history remains readable after a document is deleted or reprocessed. Each run is committed in
its own transaction; a failed run is recorded as `failed` without affecting earlier runs.

## Relationships

Institution 1 — * Application 1 — * ApplicationProgramme; Application 1 — * Document; Document 0..1 — * Document
(duplicates → original). Institutions and applications cannot be deleted while referenced (RESTRICT); no delete
endpoint exists for them.

## Document storage, duplicates and deletion

- **Layout** (root = `REGULENS_DOCUMENT_STORAGE_DIR`, default `data/documents/`): `<key[0:2]>/<key>.pdf`;
  `.incoming/` for in-progress uploads; `.trash/` for files isolated during deletion. Keys must match `^[0-9a-f]{32}$`
  and every resolved path must stay under the root, so neither filenames nor tampered keys can reach other files.
- **Consistency**: the file is moved into place after the row is flushed and before commit; commit failure removes
  the file; validation or I/O failure removes the temp file. A storage write failure records an `intake_failed` row
  without content (the only failure persisted; validation rejections are not stored).
- **Duplicate policy**: same SHA-256 within the same application → new row kept as `duplicate_detected`, linked to the
  earliest `uploaded` original. The original is never modified or overwritten. Other applications are reported only
  as a count. Same filename with different content is *not* a duplicate. Identical hashes indicate identical bytes —
  not misconduct, and not authenticity.
- **Deletion policy**: explicit hard delete (row + file), allowed in intake statuses only. Rationale: there is no audit
  subsystem yet, so retaining "soft-deleted" files would imply a retention/audit guarantee the prototype does not
  provide. Duplicate integrity: deleting an original promotes its earliest duplicate to `uploaded` and re-links the
  rest. File removal is two-phase (isolate → commit → discard; restore on failure). If a crash happens between
  commit and discard, an orphan file may remain in `.trash/` (safe: never served).
- **Reset**: `reset-data --confirm-reset` also deletes document, processing, scrutiny, verification and synthetic
  reference rows and the stored files documents reference. Scrutiny rules are kept.

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

RegulatorySource (verified official documents that rules cite), ReviewDecision (final human decision with rationale),
AuditEvent (append-only), User/Role. These will reference `applications.id` and `institutions.id`.

## Deliverable 5 tables (migration `0004`)
| Table | Purpose / key constraints |
|---|---|
| users | id, username UNIQUE, display_name, role (`reviewer`/`admin`), scrypt password_hash, is_active, timestamps |
| auth_sessions | token_hash (SHA-256) UNIQUE, user_id FK CASCADE, expires_at, revoked_at |
| finding_review_actions | append-only history: finding_id FK CASCADE (INDEX), application_id FK, action_type, previous/new status, actor (id SET NULL + username snapshot), note, evidence_refs JSON, evidence_request_id |
| evidence_requests | application_id FK RESTRICT, finding_id FK SET NULL (+ title snapshot), requested_evidence, reason, due_date, status, version, created/closed by/at, closing_note; INDEX (application_id, status) |
| evidence_request_documents | request FK CASCADE, document_id FK SET NULL + filename snapshot, linked_by/at |
| audit_events | created_at INDEX, actor, action INDEX, resource type/id, application_id INDEX (no FK so history survives), outcome, request_id, details JSON |
| alerts | dedup_key UNIQUE, application_id FK, event_type, severity, title, message, optional finding/request/document ids |
| alert_reads | (alert_id, user_id) PK — per-user read state |

`findings` gains `review_version` (optimistic concurrency) and the new review-state CHECK. The migration maps legacy
values (`acknowledged` → `confirmed`, `needs_follow_up` → `escalated`); downgrade maps back. `reset-data` also clears
review/evidence/alert rows but keeps users, rules and the audit log (and audits the reset).

## Cross-case reuse (migration 0007, additive)

| Table | Key columns |
|---|---|
| users | + `cross_case_reviewer` boolean, default false |
| document_fingerprints | document_id FK (cascade), sha256, feature_version, text_fingerprint (SHA-256 of normalised text), text_chars, pages JSON (per-page pHashes ×4 rotations, ink fraction); unique (document_id, feature_version) |
| reuse_scan_runs | application_id FK, status running/completed/failed, pipeline_version, config_version, config JSON, counts, outcome_counts, failure_reason |
| case_pairs | input_key unique (hash of document ids, SHA-256s, pipeline and config versions), document_a/b_id FK SET NULL, application_a/b_id FK RESTRICT, sha256_a/b, candidate_methods, outcome, candidate_score, pipeline/config version, review_status, review_version, first/last run, is_evaluation_fixture, ground_truth_label (CHECK: only for fixtures; never set by production scans), CHECKs for distinct applications and documents |
| match_evidence | pair_id unique FK (cascade); exact/text/visual/geometric/fields JSON, matched_pages, reasons, uncertainties, stage_status, snapshot (identities at evaluation time), config, latency_ms. Written once, never updated |
| case_pair_review_actions | append-only dispositions: action_type, previous/new status, actor, note, time |
| reuse_evaluation_runs | stored A0/A1/A4 results with dataset digest and versions |

Downgrade to 0006 drops these tables and the column. Verified on a fresh database, on a copy of a populated
0004 database (0004→0007, data preserved) and by an automated 0006→0007→0006→0007 round-trip test.
