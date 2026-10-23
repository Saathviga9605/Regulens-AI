# Requirements

ReguLens AI assists AICTE scrutiny of Extension of Approval (EoA) applications from existing technical
institutions. It is a **decision-support** tool: all approvals, rejections and misconduct determinations are made
by authorised humans.

## Compulsory capabilities (problem statement)

| # | Capability | Deliverable |
|---|-----------|-------------|
| 1 | Application and institutional-record management | Planned (D2) |
| 2 | PDF document upload and storage | Planned (D2) |
| 3 | OCR of scanned documents | Planned (D3) |
| 4 | Structured extraction with page-level evidence (document, page, text span) | Planned (D3) |
| 5 | Configurable regulatory validation rules with provenance (handbook, clause, version) | Planned (D4) |
| 6 | Cross-document consistency checks | Planned (D4) |
| 7 | Preliminary anomaly detection (flags for review, not conclusions) | Planned (D5) |
| 8 | Issuer-verification workflow (simulated; no real government APIs) | Planned (D5) |
| 9 | Reviewer dashboard and review queue | Shell in D1; queue planned (D6) |
| 10 | Audit trail of all user/system actions | Planned (D6) |
| 11 | Preliminary scrutiny reports with cited evidence | Planned (D6) |
| 12 | Human review and decision recording | Planned (D6) |
| 13 | Authentication and role-based access | Planned (D6) |

Deliverable numbers after D1 are indicative and may be re-sequenced.

## Non-functional requirements

- Evidence-first: every extracted value and every finding must cite its source.
- Rule provenance: every rule traceable to a regulatory source and version.
- Safety: no autonomous approval/rejection; anomaly ≠ misconduct; neutral wording.
- Data: synthetic institutional data only for the prototype.
- Security: no secrets in source control; explicit CORS; no internal details in API errors.
- Platform: runs locally on Windows (PowerShell) without Docker or PostgreSQL; portable to macOS/Linux.

## Deliverable 1 scope (this release)

Runnable foundation: FastAPI backend with `/api/v1/health` (real DB probe) and `/api/v1/system/info`; SQLite via
SQLAlchemy; centralised configuration, structured logging, consistent errors, CORS; React dashboard shell with
live backend status (loading / connected / degraded / disconnected, with retry); automated tests; documentation.
