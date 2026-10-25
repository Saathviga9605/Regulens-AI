# API Contracts

Base URL (development): `http://127.0.0.1:8000/api/v1`. All bodies are JSON. Every response carries an
`X-Request-ID` header. Timestamps are ISO 8601 UTC with offset (e.g. `2026-10-23T14:28:17.123456Z`).
Resources are addressed by their human-readable codes; internal UUIDs are never exposed.

## Conventions

- **Request bodies reject unknown fields** (`extra="forbid"`): sending `id`, `institution_code` (on institution
  create/update), `application_code`, `status`, `submitted_at`, `created_at` or `updated_at` returns 422.
  This prevents mass assignment. Strings are whitespace-trimmed.
- **PATCH** bodies are partial: omitted fields are unchanged; explicit `null` is rejected (422).
- **Pagination**: `page` (≥1, default 1), `page_size` (1–100, default 20). Response:
  `{"items": [...], "total": int, "page": int, "page_size": int, "total_pages": int}`.
- **Search** (`q`, ≤100 chars) is case-insensitive "contains"; `%` and `_` are matched literally.

## Errors

```json
{ "error": { "code": "invalid_status_transition", "message": "Cannot change status from 'draft' to 'preliminary_scrutiny_completed'.",
             "request_id": "3f2c…", "details": [ { "allowed_transitions": ["ready_for_preliminary_scrutiny"] } ] } }
```

| Status | `code` | When |
|--------|--------|------|
| 404 | `not_found` | Unknown route, institution or application |
| 404 | `institution_not_found` | `institution_code` in an application body does not exist (`details[0].loc = ["body","institution_code"]`) |
| 405 | `method_not_allowed` | Wrong method |
| 409 | `institution_inactive` | Creating/assigning/marking ready an application for an inactive institution |
| 409 | `application_frozen` | PATCH on a non-draft application |
| 409 | `invalid_status_transition` | Transition not permitted; `details[0].allowed_transitions` lists valid targets |
| 422 | `validation_error` | Schema or business-rule validation failed; `details[]` has `loc` and `msg` |
| 500 | `internal_error` | Unhandled error; generic message only, stack trace logged server-side with the same `request_id` |

## System

### GET /health
`200` `{"app_name","api_version","status":"ok"|"degraded","database":{"status":"ok"|"unavailable","detail"}}`.
Runs a real `SELECT 1`. Degraded still returns 200; clients read `status`.

### GET /system/info
Safe metadata: `app_name, app_version, api_version, environment, database_backend, implemented_capabilities[], planned_capabilities[]`.

## Institutions

### Institution (response)
```json
{
  "institution_code": "INST-00001",
  "name": "Deccan Ridge Institute of Engineering",
  "institution_type": "private_self_financing",
  "state": "Maharashtra",
  "district": "Pune",
  "status": "active",
  "address": "Plot 14, Synthetic Knowledge Park, …",
  "trust_name": "Deccan Ridge Education Society (Synthetic)",
  "property_identifier": "SYN-MH-PUN-S.No.101/2A",
  "created_at": "…", "updated_at": "…"
}
```
`institution_type`: `government | government_aided | private_self_financing | deemed_university | state_private_university`.
`status`: `active | inactive`.

### POST /institutions → 201 Institution
Body (all required): `name` (3–200), `institution_type`, `state` (2–80), `district` (2–80), `address` (5–500),
`trust_name` (3–200), `property_identifier` (3–100). The code is generated (`INST-00001`, …); status starts `active`.

### GET /institutions → 200 Page[Institution]
Query: `q` (name or code), `state`, `status`, `page`, `page_size`. Ordered by normalised name, then code.

### GET /institutions/{institution_code} → 200 Institution | 404

### PATCH /institutions/{institution_code} → 200 Institution | 404 | 422
Any subset of the create fields plus `status`. The code cannot change. Applications already marked ready keep their
institution snapshot (see data model).

## Applications

### ApplicationListItem (list response)
```json
{
  "application_code": "REG-EoA-2026-0001",
  "category": "extension_of_approval",
  "academic_year": "2026-27",
  "application_type": "eoa_no_change",
  "status": "draft",
  "institution": { "institution_code", "name", "institution_type", "state", "district", "status" },
  "programme_count": 2,
  "total_proposed_intake": 180,
  "submitted_at": null,
  "created_at": "…", "updated_at": "…"
}
```

### Application (detail response) = ListItem plus
```json
{
  "programmes": [ { "programme_level": "undergraduate", "course_name": "B.Tech …", "shift": "first",
                    "existing_intake": 120, "proposed_intake": 120 } ],
  "status_changed_at": "…",
  "is_editable": true,
  "allowed_transitions": ["ready_for_preliminary_scrutiny"],
  "institution_snapshot": null
}
```
`institution_snapshot` (when not draft): `institution_code, name, institution_type, state, district, address,
trust_name, property_identifier, captured_at`. `submitted_at` is the internal "marked ready" time, not an AICTE submission date.

Enums: `application_type` = `eoa_no_change | increase_in_intake | reduction_in_intake | introduction_of_new_course | change_of_institution_name`;
`programme_level` = `diploma | undergraduate | postgraduate`; `shift` = `first | second`; `status` — see data model.

### POST /applications → 201 Application
```json
{
  "institution_code": "INST-00001",
  "academic_year": "2026-27",
  "application_type": "increase_in_intake",
  "category": "extension_of_approval",
  "programmes": [ { "programme_level": "undergraduate", "course_name": "B.Tech CSE", "shift": "first",
                    "existing_intake": 60, "proposed_intake": 120 } ]
}
```
- `category` optional (only `extension_of_approval`). `shift` optional (default `first`).
- `academic_year`: `YYYY-YY`, start 2000–2099, second part = next year (e.g. `2026-27`, `2099-00`).
- `programmes`: 1–20 items; `course_name` 2–150; intakes are JSON integers 0–600 (strings/floats rejected).
- Business rules (422 with `loc` pointing at the programme field): no duplicate level+course+shift; existing
  intake > 0 except for new courses; proposed intake > 0; `increase_in_intake` needs ≥1 increase;
  `reduction_in_intake` needs ≥1 reduction; `introduction_of_new_course` needs ≥1 programme with existing 0;
  `eoa_no_change` / `change_of_institution_name` need proposed = existing.
- Institution must exist (404 `institution_not_found`) and be active (409 `institution_inactive`).
- ID is generated: `REG-EoA-{academic start year}-{4-digit sequence per year}`.

### GET /applications → 200 Page[ApplicationListItem]
Query: `q` (application ID, institution name or code), `status`, `academic_year` (`YYYY-YY`), `application_type`,
`institution_code`, `page`, `page_size`. Ordered newest first (`created_at` desc, then `application_code` desc).
Institution data is joined and programmes batch-loaded (3 queries per page, no N+1).

### GET /applications/{application_code} → 200 Application | 404

### PATCH /applications/{application_code} → 200 Application | 404 | 409 | 422
Draft only (else 409 `application_frozen`). Any of `institution_code`, `academic_year`, `application_type`,
`programmes` (replaces the full list). The merged result is validated before anything is written, so a failed
update leaves the record unchanged. The application ID never changes, even if the academic year does.

### POST /applications/{application_code}/status → 200 Application | 404 | 409 | 422
Body: `{"target_status": "<status>"}`. Values outside the enum (e.g. `approved`, `rejected`) → 422.
Disallowed transitions → 409 `invalid_status_transition`.

`ApplicationRead` also includes `document_intake_open: bool` (true for `draft` and `awaiting_additional_evidence`).

## Documents

Intake only. No OCR, classification, extraction, validation or authenticity check is performed. A SHA-256 checksum
identifies content for comparison; it does not prove authenticity.

### Document (response)
```json
{
  "id": "c1844bca-4ce6-4e29-b949-3792329a28b2",
  "application_code": "REG-EoA-2026-0001",
  "original_filename": "synthetic-fire-safety.pdf",
  "category": "fire_safety_certificate",
  "mime_type": "application/pdf",
  "size_bytes": 435,
  "sha256": "a7f38d52…",
  "status": "uploaded",
  "duplicate_of": null,
  "other_application_match_count": 0,
  "content_available": true,
  "description": null,
  "uploaded_at": "…", "created_at": "…", "updated_at": "…"
}
```
- `category`: `fire_safety_certificate | occupancy_certificate | completion_certificate | building_license | form_d | structural_stability_certificate | building_plan | university_noc | trust_resolution | other`.
  Categories are organisational; none is mandatory.
- `status`: `uploaded | duplicate_detected | intake_failed`.
- `duplicate_of` (when `duplicate_detected`): `{id, original_filename, category, uploaded_at}` of the original in the
  **same** application.
- `other_application_match_count`: number of other applications holding identical content — no identifiers.
- `content_available`: false when intake failed or the stored file is missing.
- Storage keys and filesystem paths are never returned.

### GET /documents/intake-policy → 200
`{"max_upload_bytes": 20971520, "accepted_content_types": ["application/pdf"], "accepted_extensions": [".pdf"],
"categories": [...], "intake_open_statuses": ["draft", "awaiting_additional_evidence"]}`

### POST /applications/{application_code}/documents → 201 Document
`multipart/form-data`: `file` (required), `category` (required), `description` (optional, ≤500 chars).

| Status | `code` | When |
|--------|--------|------|
| 404 | `not_found` | Application does not exist |
| 409 | `document_intake_closed` | Application not in `draft` / `awaiting_additional_evidence` |
| 413 | `payload_too_large` | File (or request body) exceeds `REGULENS_MAX_UPLOAD_BYTES` |
| 415 | `unsupported_file_type` | Extension not `.pdf`, or declared content type not PDF-compatible (`application/pdf`, `application/x-pdf`, `application/octet-stream` or empty are tolerated) |
| 415 | `invalid_pdf_signature` | Content does not start with `%PDF-` |
| 415 | `invalid_pdf_structure` | No `%%EOF` in the last 1 KiB (truncated/incomplete) |
| 422 | `empty_file` / `invalid_filename` / `validation_error` | Empty file; empty name or forbidden characters (`<>:"|?*`, control chars) or >255 chars; missing/invalid category |
| 500 | `document_storage_failed` | File could not be written; an `intake_failed` row is recorded (`details[0].document_id`) |

The filename is reduced to its base name (`../../x.pdf` → `x.pdf`) and used only for display and
`Content-Disposition`. Rejected uploads leave no file and no row.

### GET /applications/{application_code}/documents → 200 Page[Document]
`page`, `page_size` (≤100). Ordered by `uploaded_at`, then `id`. 404 if the application does not exist.

### GET /documents/{document_id} → 200 Document | 404

### GET /documents/{document_id}/content → 200 application/pdf | 404 | 422
Query `disposition=inline` (default) or `attachment`. Headers: `Content-Type: application/pdf`,
`Content-Disposition: <disposition>; filename="<ASCII-safe>"; filename*=UTF-8''<percent-encoded>`,
`X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`. 404 `content_unavailable` when the stored
file is missing or the stored key is invalid.

### DELETE /documents/{document_id} → 204 | 404 | 409
Permanent deletion of the row and the stored file (409 `document_intake_closed` outside intake statuses). If the
document is an original with duplicates, the earliest duplicate becomes `uploaded` and the remaining duplicates are
re-linked to it. A missing stored file does not block deletion.

`DocumentRead` also includes `processing`: `null` or
`{status, pipeline_version, is_current, predicted_category, classification_confidence, warning_count, finished_at}`.

## Document processing

Synchronous within the request; bounded by `REGULENS_MAX_PROCESSING_PAGES` and OCR timeouts. Error responses never
contain filesystem paths or stack traces. Details: [scrutiny-and-extraction.md](scrutiny-and-extraction.md).

### POST /documents/{document_id}/processing[?force=true] → 200 ProcessingResult | 404 | 409
409 `document_not_processable` for intake-failed documents. Returns the cached result (`reused_from_cache: true`)
when content and pipeline version are unchanged, unless `force=true`.

```json
{
  "document_id": "…", "application_code": "REG-EoA-2026-0005",
  "status": "completed | completed_with_warnings | failed",
  "failure_code": "ocr_unavailable", "failure_reason": "No page has a usable text layer and OCR is not available. …",
  "pipeline_version": "p1+cls-1+label_regex_v1", "is_current": true, "reused_from_cache": false,
  "ocr_available": false, "page_count": 1, "pages_processed": 1, "warnings": ["…"],
  "classification": {"predicted_category": "occupancy_certificate", "selected_category": "occupancy_certificate",
                     "confidence": "high | medium | uncertain", "score": 0.92,
                     "signals": [{"signal": "phrase 'occupancy certificate'", "weight": 10, "in_heading": true}],
                     "alternatives": [], "agrees_with_selected": true},
  "pages": [{"page_number": 1, "method": "text_layer | ocr | none",
             "status": "ok | insufficient_text | ocr_failed | ocr_low_text", "char_count": 412, "warnings": []}],
  "fields": [{"id": "…", "document_id": "…", "field_name": "survey_number", "raw_value": "318",
              "normalized_value": {"text": "318"}, "page_number": 1, "evidence_quote": "Survey No.: 318",
              "method": "label_regex_v1", "confidence": "high | medium | low",
              "status": "extracted | not_found | ambiguous | unverified", "warnings": [], "candidates": []}],
  "started_at": "…", "finished_at": "…"
}
```
`normalized_value`: `{"date": "YYYY-MM-DD"}`, `{"value", "unit": "sq_m|sq_ft|null", "value_sq_m"}`, or `{"text"}`;
`null` when not safely normalisable (e.g. ambiguous date — `raw_value` keeps the original).

### GET /documents/{document_id}/processing → 200 ProcessingResult | 404 (`not_found` / `not_processed`)
### GET /documents/{document_id}/pages → 200 Page[{page_number, method, status, char_count, text, warnings}]

## Simulated issuer verification

### POST /documents/{document_id}/issuer-verifications → 201 | 404 | 409 `document_not_processed`
### GET /documents/{document_id}/issuer-verifications → 200 [Attempt] (latest 50)
### GET /applications/{application_code}/issuer-verifications → 200 Page[Attempt]
```json
{"id": "…", "document_id": "…", "document_filename": "occupancy-certificate.pdf",
 "adapter": "mock_synthetic_registry", "method": "simulated_reference_lookup", "simulated": true,
 "simulation_label": "SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY",
 "outcome": "simulated_match | simulated_mismatch | simulated_expired | simulated_unavailable | manual_review | unsupported",
 "explanation": "…", "fields_compared": [{"field": "institution_name", "document_value": "…", "result": "match | mismatch | not_available | no_reference"}],
 "reference_code": "SYN-REF-0004", "created_at": "…"}
```
Synthetic reference values are never returned.

## Scrutiny rules

### GET /scrutiny-rules → 200 [Rule]  ·  GET /scrutiny-rules/{rule_id} → 200 | 404
`Rule`: `rule_id, title, description, rule_type, parameters, severity (info|low|medium|high), enabled, source,
source_reference, source_verification_status (verified|unverified|not_applicable), is_demo_only,
provenance (regulatory|checklist|integrity|demo), registry_managed, retired, effective_from, effective_to, version,
created_at, updated_at`.

### POST /scrutiny-rules → 201 | 409 `rule_exists` | 422
Body: `rule_id` (`^[A-Z]{2,6}-\d{3}$`), `title`, `description`, `rule_type`, `parameters`, `severity`, optional
`enabled`, `source`, `source_reference`, `source_verification_status` (default `unverified`), `is_demo_only`
(default `true`). Parameters are validated against the rule type's schema; unknown keys → 422.
`alternative_document_group` requires an explicit non-empty `application_types` list and an operator-supplied
validity reference date. This evaluator is infrastructure only; no APH rule is seeded or active.

### PATCH /scrutiny-rules/{rule_id} → 200 | 404 | 409 `registry_rule_immutable` | 422
For non-registry rules, any of `title, description, parameters, severity, enabled, source, source_reference,
source_verification_status, is_demo_only`. `rule_type`, `rule_id` and `version` cannot be set. A real change
increments `version`. For a registry-managed rule, only `enabled` may be changed; that transition is audited.
The approved registry importer and append-only rule-version storage are not implemented yet.

## Scrutiny runs and findings

Runs and findings are addressed under their application; a run/finding of another application returns 404.

### POST /applications/{application_code}/scrutiny-runs → 201 Run | 404 | 409 `scrutiny_run_in_progress` | 422
Optional body `{"scrutiny_date": "YYYY-MM-DD", "ruleset_profile": "production|aph_eoa_demo"}`.
`ruleset_profile` defaults to `production`; `aph_eoa_demo` explicitly selects the isolated APH demo profile and does
not alter production activation. The demo profile is limited to existing private self-financing technical
institutions and rejects an explicit `scrutiny_date` so its date basis cannot be overridden;
an explicit production-profile `scrutiny_date` is labelled `operator_override`;
otherwise the internal application `submitted_at` (marked-ready) calendar date is used. If unavailable, the date
and source are null/`unavailable`; the system date is never substituted.
Processes documents with missing/stale results first. An unexpected engine error yields a run with
`status: "failed"` and a generic `failure_reason`; earlier runs are untouched.

### GET /applications/{application_code}/scrutiny-runs → 200 Page[RunSummary] (newest first)
### GET /applications/{application_code}/scrutiny-runs/{run_id} → 200 Run | 404
`RunSummary`: `id, application_code, run_number, status (running|completed|completed_with_warnings|failed),
scrutiny_date, scrutiny_date_source, ruleset_profile, ruleset_profile_version, rule_set_version, summary {evaluation_outcomes, finding_severities, rule_findings, anomaly_indicators,
documents_considered, documents_processed_ok, rules_evaluated}, warnings, failure_reason, started_at, finished_at`.
`Run` adds `rule_snapshot` (demo snapshots include candidate ID and citation), `documents_considered` and `evaluations[]`
(`rule_id, rule_version, subject_key, outcome (pass|issue|inconclusive|not_applicable), severity, explanation,
document_ids, field_ids, evidence[], compared_values[], missing_evidence, human_review_recommended`).

### GET /applications/{application_code}/scrutiny-runs/{run_id}/findings → 200 Page[Finding]
### GET /applications/{application_code}/findings → 200 Page[Finding] (latest run; empty page if none)
Filters: `severity`, `kind` (`rule_finding | anomaly_indicator`), `outcome`, `review_status`; `page`, `page_size ≤ 100`.
`Finding`: `id, run_id, finding_key (stable across runs), kind, finding_type, title, severity, outcome, explanation,
uncertainty, rule_id, rule_version, detector, document_ids, field_ids, evidence[{document_id, document_filename,
field_id, field_name, value, page_number, quote}], compared_values, missing_evidence, human_review_recommended,
review_status (not_reviewed|acknowledged|needs_follow_up|dismissed), review_note, reviewed_at, created_at`.

### GET /applications/{application_code}/findings/{finding_id} → 200 FindingDetail | 404
Adds `application_code`, `run_number` and `rule` (the rule as snapshotted for that run, incl. source and demo flag).

### PATCH /applications/{application_code}/findings/{finding_id}/review → 200 FindingDetail | 404 | 422
Body `{"review_status": "...", "review_note": "≤1000 chars"}`. Records a human assessment; the system outcome and
the application status are not changed.

## CORS
Allowed origins from `REGULENS_CORS_ORIGINS` (exact match); credentials not allowed; `*` rejected in production.
`/docs` and `/openapi.json` are served outside production only.

## Deliverable 5 endpoints

All require `Authorization: Bearer <token>` except login (401 `not_authenticated` otherwise). Admin-only routes
return 403 `forbidden` to reviewers. Details and state tables: [review-workflow.md](review-workflow.md),
[security.md](security.md).

| Method & path | Role | Notes |
|---|---|---|
| `POST /auth/login` `{username, password}` | public | → `{token, token_type, expires_at, user}`; 401 `invalid_credentials`; 429 `too_many_attempts` |
| `POST /auth/logout` | any | 204, revokes session |
| `GET /auth/me` | any | current user |
| `GET /users`, `POST /users`, `PATCH /users/{id}` | admin | create `{username, display_name, role, password≥10}`; patch `{display_name?, role?, is_active?, password?}`; 409 `user_exists` / `self_lockout` |
| `GET /review-queue` | any | `q, status, scrutiny_status, severity, unresolved_only, review_state, sort, page, page_size` → `{items, total, page, page_size, total_pages, counts}` |
| `POST /applications/{code}/findings/{id}/actions` | any | `{action, expected_version, note?, evidence_refs?[], requested_evidence?, due_date?}` → 201 action; 409 `invalid_review_transition` / `stale_review` / `finding_superseded`; 422 `reason_required` |
| `GET /applications/{code}/findings/{id}/actions` | any | review history (oldest first) |
| `GET /applications/{code}/review-actions` | any | latest 100 actions for the application |
| `GET /applications/{code}/evidence-requests?status=open\|fulfilled\|cancelled\|overdue` | any | list |
| `POST /applications/{code}/evidence-requests` | any | `{requested_evidence, reason≥10, due_date?, finding_id?}` |
| `POST …/evidence-requests/{id}/documents` `{document_id}` | any | explicit link; 409 `already_linked` / `evidence_request_closed` |
| `POST …/evidence-requests/{id}/fulfil` `{expected_version, note?}` | any | 409 `no_linked_evidence` / stale |
| `POST …/evidence-requests/{id}/cancel` `{expected_version, note≥10}` | any | |
| `POST /applications/{code}/documents` | any | new optional form field `evidence_request_id` (must be an open request of the same application) |
| `GET /audit-events` | admin | filters `action` (prefix), `actor`, `outcome`, `resource_type`, `application_code`; paginated, newest first; **no PUT/PATCH/DELETE** |
| `GET /applications/{code}/audit-events` | any | same, scoped to one application |
| `GET /alerts` | any | `unread_only, application_code, event_type, page, page_size` → page + `unread_count`; refreshes due/overdue alerts |
| `POST /alerts/read` `{alert_ids[]}` / `POST /alerts/read-all[?application_code]` | any | 204, per-user read state |
| `GET /applications/{code}/scrutiny-runs/{run}/report.pdf` | any | PDF attachment; 404 if the run belongs to another application; 409 `run_not_reportable` for failed/running runs |
| `POST /applications/{code}/copilot` `{question 2–500, finding_id?}` | any | → `{intent, lines[], sources[{id, kind, label, finding_id, document_id, document_filename, page_number, quote}], grounded, limitations[], disclaimer, suggestions[]}` |

Changed: findings now include `review_version` and `allowed_actions`; review states are
`not_reviewed | confirmed | dismissed | escalated | awaiting_evidence | resolved`. The previous
`PATCH …/findings/{id}/review` endpoint was **removed** (replaced by review actions). Document content and reports
require the bearer header; `Content-Disposition` is exposed via CORS.
