# Implementation Status

Last verified: 2026-10-23 on Windows 11, Python 3.13.14, Node 24.19.0 / npm 11.17.0.

Statuses: **Implemented and tested** · **Implemented but not fully tested** · **Planned** · **Blocked**

## Deliverable 1 — Foundation (re-verified in Deliverable 2)

| Feature | Status | Evidence |
|---------|--------|----------|
| FastAPI app factory, `/api/v1`, request IDs, CORS allow-list | Implemented and tested | `test_health.py`, `test_cors_and_config.py` |
| `GET /health` with real DB query; degraded reporting | Implemented and tested | `test_health.py`; live in browser run |
| `GET /system/info` (safe metadata) | Implemented and tested | `test_system_info.py` |
| Consistent errors; 500 hides internals | Implemented and tested | `test_errors.py` |
| Structured JSON logging | Implemented but not fully tested | observed in server output only |
| Dashboard shell, connection indicator, retry | Implemented and tested | `dashboard.test.tsx`; real browser |

## Deliverable 2 — Institutions and EoA applications

| Feature | Status | Evidence |
|---------|--------|----------|
| Alembic migrations (fresh + existing DB, repeatable, data preserved) | Implemented and tested | `test_seed_and_migrations.py` |
| Institution model, generated unique codes | Implemented and tested | `test_institutions.py` |
| Institution create / list / paginate / search / detail / update | Implemented and tested | `test_institutions.py` |
| Rejection of client-set codes, ids, timestamps, nulls (mass assignment) | Implemented and tested | both API test files |
| Application model + programmes, FK and CHECK constraints | Implemented and tested | `test_applications.py` |
| Concurrency-safe application IDs | Implemented and tested | `test_concurrent_creation_produces_unique_ids` (24 creates, 8 threads) |
| Application create / list / filters / search / detail | Implemented and tested | `test_applications.py` |
| No N+1 in list | Implemented and tested | `test_list_avoids_n_plus_one` (≤3 SELECTs) |
| Academic-year, intake and programme/type validation | Implemented and tested | parametrised tests |
| Draft editing; freezing after ready; atomic failed updates | Implemented and tested | `test_draft_update`, `test_frozen_…`, `test_failed_update_…` |
| Workflow transitions (valid, invalid, terminal, return to draft) | Implemented and tested | `test_applications.py` |
| Institution snapshot not rewritten by later edits | Implemented and tested | `test_institution_edit_does_not_rewrite_frozen_snapshot` |
| Persistence across sessions/restarts | Implemented and tested | `test_persistence_across_sessions_and_restarts`; browser reload |
| Synthetic seed, idempotent reseed, user records untouched | Implemented and tested | `test_seed_and_migrations.py`; CLI run twice |
| Guarded `reset-data` | Implemented and tested | `test_reset_requires_…`, `test_cli_reset_without_flag_refuses` |
| Frontend: applications list (loading/empty/error, search, filters, pagination) | Implemented and tested | `applications.test.tsx`; real browser |
| Frontend: application create (validation, server field errors, navigation) | Implemented and tested | `applications.test.tsx`; real browser |
| Frontend: application detail, draft edit, status actions | Implemented and tested | `applications.test.tsx`; real browser |
| Frontend: institutions list/search/detail/create/edit, linked applications | Implemented and tested | `institutions.test.tsx`; real browser |

## Later deliverables

| Feature | Status |
|---------|--------|
| PDF upload & storage | Planned (next) |
| OCR, evidence-linked extraction | Planned |
| Regulatory rules with provenance, consistency checks | Planned |
| Anomaly detection, simulated issuer verification | Planned |
| Review queue, human decisions, audit trail, reports | Planned |
| Authentication & roles | Planned |

## Verification log (2026-10-23)

| Check | Result |
|-------|--------|
| Baseline before changes | 12 backend passed, 8 frontend passed, tsc clean, build OK (matched report) |
| `python -m pytest` | **66 passed** (12 existing + 54 new) |
| `npm test` | **27 passed** (8 existing, 1 adapted to new routes + 19 new) |
| `npm run typecheck` | 0 errors |
| `npm run build` | success (247 kB JS / 76 kB gzip) |
| Seed run twice (CLI) | 8+12 created, then 0 created / 8+12 already present |
| `reset-data` without flag | refused, exit code 2 |
| Real browser E2E (Playwright driving headless Microsoft Edge, scratch DB) | all 14 acceptance steps passed; screenshots inspected (desktop + 390 px mobile) |

## Known limitations

- Application creation form loads at most the first 100 active institutions (alphabetical) into the selector.
- Academic-year choices in the UI are fixed to 2024-25 … 2027-28 (the API accepts any valid year).
- The ID-sequence upsert is SQLite-dialect specific.
- Status changes record no actor or note yet (audit trail is a later deliverable).
- No authentication: anyone who can reach the API can change data. Dev/local use only.
- Browser E2E script lives outside the repo (not part of the automated suite).
- Port 5173 is occupied by an unrelated app on the verification machine; browser checks used port 5180.
