# Implementation Status

Last verified: 2026-10-24 (Deliverable 6) on Windows 11, Python 3.13.14, Node 24.19.0 / npm 11.17.0.

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

## Deliverable 3 — Document intake, storage and integrity

| Feature | Status | Evidence |
|---------|--------|----------|
| `documents` table via migration `0002` (existing data preserved) | Implemented and tested | `test_migrations_preserve_existing_data_and_are_repeatable` |
| Upload to existing / nonexistent application | Implemented and tested | `test_upload_valid_pdf`, `test_upload_to_nonexistent_application` |
| Empty, non-PDF, misleading MIME, bad signature, truncated, bad filename rejection | Implemented and tested | `test_rejected_uploads_leave_nothing_behind` (10 cases) |
| Size limit (streamed and Content-Length) | Implemented and tested | `test_oversized_upload_rejected` |
| Streaming SHA-256, server-generated storage keys | Implemented and tested | upload + integrity tests |
| Exact duplicate detection (same app), cross-app count only | Implemented and tested | `test_exact_duplicate_…`, `test_match_in_other_application_…` |
| Same filename / different content; many per category | Implemented and tested | dedicated tests |
| Persistence across sessions/restarts | Implemented and tested | `test_metadata_persists_across_sessions`; browser reload |
| Content delivery (inline/attachment, safe headers, integrity) | Implemented and tested | `test_content_download_integrity_and_headers`; browser download sha256 match |
| Missing document / missing file handling | Implemented and tested | `test_missing_document_and_missing_content` |
| Path traversal (filename, id, tampered key) | Implemented and tested | 4 traversal tests |
| Cleanup on DB failure; `intake_failed` on storage failure | Implemented and tested | `test_database_failure_…`, `test_storage_failure_…` |
| Deletion: duplicate, original promotion, missing file, rollback restore | Implemented and tested | 4 deletion tests; browser |
| Intake only in draft / awaiting evidence | Implemented and tested | `test_intake_closed_…`; frontend test; browser |
| Not served statically; storage dir inside `frontend/` rejected | Implemented and tested | `test_documents_are_not_served_statically`, config test; live curl checks |
| Reset also removes documents and their files | Implemented and tested | `test_reset_removes_documents_and_their_files` |
| Frontend documents panel (inventory, upload, validation, duplicate display, details, open/download, confirmed delete, errors) | Implemented and tested | `documents.test.tsx` (13); browser |
| Upload progress percentage | Not implemented — "Uploading…" busy state only (fetch has no upload progress) | — |

## Deliverable 4 — Document intelligence, preliminary scrutiny and simulated verification

| Feature | Status | Evidence |
|---------|--------|----------|
| Migration `0003` (additive; existing data preserved) | Implemented and tested | migration tests; ran on existing scratch DBs |
| Page-level text extraction (PyMuPDF), 1-based pages | Implemented and tested | `test_text_pdf_extracts_pages_with_one_based_numbers`; browser |
| OCR-unavailable behaviour (failed `ocr_unavailable`, never empty success) | Implemented and tested | `test_ocr_unavailable_…`; browser (no Tesseract on this machine) |
| OCR fallback path / OCR failure handling | Implemented and tested (stub engine) | `test_ocr_fallback_…`, `test_ocr_failure_reported` |
| OCR with real Tesseract | **Implemented but not fully tested** | `test_real_tesseract_ocr` **skipped**: Tesseract not installed on the verification machine |
| Corrupt / empty / encrypted / missing-file PDFs | Implemented and tested | parametrised tests; encrypted demo PDF in browser run |
| Caching by checksum + pipeline version; force reprocess; cross-document reuse | Implemented and tested | `test_results_cached_…` |
| Classification with signals, documented confidence, uncertain outcome; mismatch warning, selected category kept | Implemented and tested | classification tests; browser |
| Evidence-grounded extraction; grounding check; not found / ambiguous; no inferred validity | Implemented and tested | extraction tests |
| Date and area normalisation | Implemented and tested | parametrised tests |
| Rules as validated data; enable/disable; versioning; create; snapshot per run | Implemented and tested | rule tests; rules page in browser |
| Rule families: expected document, required field, processing quality, classification, name/identifier/address/area consistency, date order, explicit expiry, simulated issuer outcome | Implemented and tested | `test_scrutiny.py` on the demo dataset |
| Inconclusive instead of conflict for ambiguous/ungrounded values | Implemented and tested | `test_ambiguous_or_ungrounded_values_…` |
| Anomaly indicators (duplicate, cross-application content, certificate-number reuse, mixed signals, incremental saves) | Implemented and tested (duplicate, certificate reuse); others implemented but not directly asserted | tests + browser |
| Runs: history, determinism, stable finding keys, failure recording, concurrent-run guard | Implemented and tested | run tests; browser rerun |
| Findings with evidence; detail; human review status (separate from system result) | Implemented and tested | backend + frontend tests; browser |
| Application scoping of runs/findings | Implemented and tested | `test_records_are_scoped_to_their_application` |
| Simulated issuer adapter: all outcomes, labels, no fabricated match, no reference leakage | Implemented and tested | `test_simulated_issuer_…`, `test_no_match_…`; browser |
| Demo seed (12 fictional PDFs, 4 synthetic references), idempotent, user data preserved | Implemented and tested | seed tests; CLI run twice |
| Frontend: processing controls, fields/evidence, page text, simulated checks, scrutiny panel, findings filters/detail/review, run history, rules page | Implemented and tested | `scrutiny.test.tsx` (13); browser |

## Deliverable 5 — Reviewer workspace, decisions, audit, alerts, report, copilot

| Feature | Status | Evidence |
|---------|--------|----------|
| Migration `0004` (new tables; legacy review values mapped; downgrade/upgrade checked) | Implemented and tested | manual migration check with legacy data; migration test |
| Local auth: scrypt hashes, hashed bearer sessions, expiry, revocation, lockout, logout | Implemented and tested | `test_auth.py`; browser sign-in/out |
| Roles enforced server-side (rules, users, global audit = admin) with audited denials | Implemented and tested | `test_reviewer_cannot_use_admin_endpoints`; browser |
| User management (create, role change, deactivate, no self-lockout) | Implemented and tested | `test_admin_user_management`; browser |
| Review queue with filters, counts, stable sort, pagination | Implemented and tested | `test_review_queue_…`; browser |
| Review actions with reasons, transitions, optimistic concurrency, history, carry-forward | Implemented and tested | `test_review_actions_…`, `test_invalid_transitions_…`; browser |
| Evidence requests: create, explicit link at upload or later, fulfil, cancel, overdue | Implemented and tested | evidence tests; browser |
| Application-level append-only audit (no update/delete API) | Implemented and tested | `test_audit_trail_…`; browser |
| Alerts with dedup, per-user read state, due/overdue | Implemented and tested | alert tests; browser |
| Preliminary scrutiny PDF (content, escaping, auth, audit) | Implemented and tested | report tests; browser download inspected |
| Deterministic grounded copilot (intents, citations, refusals, isolation, injection-safe) | Implemented and tested | 13 copilot tests; browser |
| Frontend: sign-in, queue, review actions, evidence, alerts, copilot, report, audit, users, read-only rules | Implemented and tested | `workspace.test.tsx` (16) + updated suites |
| Per-application reviewer assignment | Planned | not implemented — all reviewers see all applications |

## Deliverable 6 — Government-grade UI revamp and local demo accounts

| Feature | Status | Evidence |
|---------|--------|----------|
| Design tokens and typed component library (fields, password toggle, dialogs, confirm dialogs, toasts, tabs, breadcrumbs, skeletons, progress, empty/error states) | Implemented and tested | `shell.test.tsx` (dialog focus trap/restore, Escape, double submit, toasts, tabs); [design-system.md](design-system.md) |
| Shell: header with original mark, environment badge, unread alerts, account menu; grouped navigation; persistent trust notice; mobile drawer | Implemented and tested | `shell.test.tsx`, `dashboard.test.tsx`; browser at 360–1920 px |
| Overview with live queue counts, priorities, recent alerts and applications | Implemented and tested | `dashboard.test.tsx`; browser |
| Login: show/hide password, lockout and missing-field messages, demo indicator, no credentials rendered | Implemented and tested | `shell.test.tsx`, `workspace.test.tsx`; browser |
| Confirmations: document delete, rule enable/disable/severity, user role and active state | Implemented and tested | `documents.test.tsx`, `scrutiny.test.tsx`, `workspace.test.tsx`; browser (cancel sends nothing) |
| Application workspace section navigation, breadcrumbs, responsive tables | Implemented and tested | browser overflow sweep (no page-level horizontal scroll on 14 routes × 6 widths) |
| Help & About page | Implemented and tested | `shell.test.tsx` |
| Demo account bootstrap from env (idempotent, hashed, production-guarded, never printed or audited) | Implemented and tested | `test_demo_bootstrap.py` (6) |
| Repo-owned browser smoke script (`npm run smoke`, opt-in writes) | Implemented and tested | passed twice consecutively on a scratch DB |
| Automated contrast audit (axe or similar) | Planned | colours chosen for WCAG AA; not tool-audited |

## Later deliverables

| Feature | Status |
|---------|--------|
| Verified regulatory sources for rules (replacing demo-only expectations) | Planned |
| Background processing worker | Planned (only if needed) |
| Real issuer integrations | Not planned without official authorisation |

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

## Verification log — Deliverable 3 (2026-10-23)

| Check | Result |
|-------|--------|
| Baseline before changes | 66 backend, 27 frontend, tsc clean, build OK |
| `python -m pytest` | **104 passed** (66 existing + 38 new) |
| `npm test` | **40 passed** (27 existing + 13 new) |
| `npm run typecheck` / `npm run build` | 0 errors / success |
| Real browser E2E (Playwright + headless Edge, scratch DB and storage) | all 12 acceptance steps passed; screenshots inspected |
| Direct access to stored files | backend: 404 for every guessed path; Vite: `/@fs/` to repo `data/` → 403, other paths return the SPA HTML, never file bytes |

## Verification log — Deliverable 4 (2026-10-23)

| Check | Result |
|-------|--------|
| Baseline before changes | 104 backend passed, 40 frontend passed, tsc clean, build OK |
| `python -m pytest` | **171 passed, 1 skipped** (skip = real Tesseract test; not installed) |
| `npm test` | **53 passed** (40 existing + 13 new) |
| `npm run typecheck` / `npm run build` | 0 errors / success (295 kB JS, 88 kB gzip) |
| `npm audit` | 0 vulnerabilities |
| Seed run twice | 12 demo documents + 4 references created, then 0 |
| Real browser E2E (Playwright + headless Edge, scratch DB/storage, OCR unavailable) | all 12 acceptance steps passed; screenshots inspected |

## Verification log — Deliverable 5 (2026-10-24)

| Check | Result |
|-------|--------|
| Baseline before changes | 171 passed + 1 skipped backend, 53 frontend, tsc clean, build OK |
| `python -m pytest` | **204 passed, 1 skipped** (skip = real Tesseract) |
| `npm test` | **71 passed** |
| `npm run typecheck` / `npm run build` | 0 errors / success |
| Real browser E2E (Playwright + headless Edge, scratch DB, demo accounts from env) | all 14 acceptance steps passed |

## Verification log — Deliverable 6 (2026-10-24)

| Check | Result |
|-------|--------|
| `python -m pytest` | **210 passed, 1 skipped** (skip = real Tesseract) |
| `npm test` | **80 passed** (7 files) |
| `npm run typecheck` / `npm run build` / `npm audit` | 0 errors / success / 0 vulnerabilities |
| Demo passwords in `frontend/dist` or `src` | none found |
| Real browser (Edge headless via Playwright), scratch DB on ports 8030/5195 | login, overview, queue, scrutiny, finding action (double-click → 1 audit event), upload, delete dialog (cancel/confirm), copilot citation, report PDF, reviewer 403, rule and user confirmations, audit without secrets; no page overflow at 360/390/768/1024/1440/1920; mobile drawer and dialog fit; only console error = intentional wrong-password 401 |
| Screenshots reviewed | login, overview, workspace with delete dialog, mobile drawer |

## Known limitations

- Application creation form loads at most the first 100 active institutions (alphabetical) into the selector.
- Academic-year choices in the UI are fixed to 2024-25 … 2027-28 (the API accepts any valid year).
- The ID-sequence upsert is SQLite-dialect specific.
- PDF checks are structural (signature, `%%EOF`); a crafted file can pass them. Files are never executed or
  rendered by the backend, but the PDF is opened by the user's browser viewer.
- No malware scanning, no encryption at rest. Upload progress is an indeterminate bar (fetch exposes no byte progress).
- Duplicate detection is exact-byte only; re-saved or re-scanned copies are not detected (by design).
- A crash between delete-commit and file discard can leave an orphan file in `.trash/`.
- Extraction recognises only `Label: value` lines in English; tables, multi-line values and unusual wording are missed.
  Accuracy has only been checked on synthetic documents and says nothing about real certificates.
- Classification confidence is a keyword heuristic, not a calibrated probability.
- All default expectation rules are demo-only and unverified against official sources; no regulatory citation exists.
- Issuer verification is simulated against synthetic records only; there is no real integration.
- Processing and scrutiny run synchronously in the HTTP request; very large or many scanned documents will be slow.
- Authentication is a local prototype scheme (no SSO/MFA/password reset); every reviewer can access every
  application; the audit log is application-level append-only, not tamper-evident or certified.
- The copilot is keyword-intent based: unusual phrasings fall back to help text; it summarises stored records only.
- Report fonts cover Latin text; other scripts may not render. Review queue counts are computed in memory.
- Alerts are visible to all staff; there are no email/SMS notifications.
- The browser smoke script (`frontend/e2e/smoke.mjs`) is manual: it needs running servers and is not part of `npm test`.
- Local demo credentials are public defaults; they must be changed before sharing (see security.md).
- Ports 8000 and 5173 were in use on the verification machine; browser checks used scratch servers on 8030/5195.
