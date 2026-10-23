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
- `category`: `fire_safety_certificate | occupancy_certificate | completion_certificate | structural_stability_certificate | building_plan | university_noc | trust_resolution | other`.
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

## CORS
Allowed origins from `REGULENS_CORS_ORIGINS` (exact match); credentials not allowed; `*` rejected in production.
`/docs` and `/openapi.json` are served outside production only.
