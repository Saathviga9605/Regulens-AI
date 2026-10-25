# Rules Registry Implementation Plan

**Status:** In progress — evaluator/date foundations, retirement of two false-positive demo rules, local-only source extraction, exact-quote validation, eight blocked APH Annexure-2 section 2.1 draft records, and evaluator support for document alternatives are implemented. The new evaluator is not seeded as an APH rule. Independent source/amendment/reuse checks, approval enforcement, append-only registry versions, approved import, and live citations remain pending.
**Date:** 2026-10-25
**Inputs:** Rules Registry Build Plan (Part 3) and the user-approved finding decisions in this chat.
**Handbook source path supplied:** `C:\Users\DELL\OneDrive\Desktop\Regulens-AI\docs\APH Final.pdf`. The PDF is present in the workspace and is explicitly Git-ignored. Its contents, edition, amendments, reuse rights, and source hash remain unverified and must be recorded before handbook-derived rules are drafted or approved.

## Summary

Build a local, verifiable pipeline that converts an identified Approval Process Handbook edition into a versioned rules registry. Keep source acquisition, verbatim extraction, clause triage, candidate drafting, human approval, and backend import as separate steps. Only approved registry rules are exported. Drafts remain in the local registry workspace and are never evaluated by the backend.

The registry supports four provenance classes: `regulatory`, `checklist`, `integrity`, and `demo`. Any rule claiming a regulatory basis must cite exact handbook text. Checklist rules cite their own checklist source; integrity rules describe technical checks and do not require a regulatory clause; demo rules remain explicitly labelled. Assumptions are not a provenance class or rule basis: unresolved values remain null/inconclusive, and human-supplied values such as a reference date are stored as labelled configuration.

The backend receives approved rules only. Imported registry-managed rule content is immutable through PATCH; only an audited `enabled` toggle is permitted. New approved versions are appended, and each scrutiny snapshot records a canonical `rule_hash` plus its clause, page, and quote hashes. Findings and PDF reports resolve the immutable rule version so they can show the clause, page, quote, and registry version that produced the result. Source PDFs, full extracted text, and unapproved candidates stay out of Git; commit provenance metadata and approved rules containing only permitted short quotes.

## Technical Context

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, SQLite.
- **Current rule surfaces:** `backend/app/models/enums.py`, `backend/app/models/scrutiny.py`, `backend/app/schemas/scrutiny.py`, `backend/app/services/rule_catalog.py`, `backend/app/services/scrutiny.py`, `backend/app/api/v1/scrutiny.py`.
- **Current extraction/cache surfaces:** `backend/app/services/extraction.py` and `backend/app/services/processing.py`. Keep extraction fields fixed in the initial registry release. If extraction becomes registry-driven later, include a deterministic hash of the per-category field lists in `PIPELINE_VERSION` before using those lists to invalidate or reuse cached processing results.
- **Registry:** root-level `rules-registry/`, separate from the backend. The backend loads only a validated approved registry; it never reads the handbook PDF or full extracted text.
- **Migrations:** add schema changes via Alembic; retain compatibility with fresh and existing SQLite databases.
- **Validation:** focused pytest coverage for extraction, quote verification, registry validation, import, rule versioning, API behavior, and migration preservation. Run frontend typecheck/tests if the displayed rule contract changes.
- **Source constraint:** `docs\APH Final.pdf` is present, but its edition, amendments, contents, and terms have not yet been verified. No clause reference, page, quote, effective date, norm, or authority is treated as verified before checking the source.

## Safety and Design Decisions

1. **No draft export:** candidate files remain in the local `rules-registry/candidates/` workspace. There is no draft or shadow rule in the backend. A future shadow feature is out of scope and must add `evaluation_mode` (`live`/`shadow`), separate result storage, exclusion from queue/report/copilot, and tests for each exclusion.
2. **Append-only registry versions:** imported registry-managed rule content is immutable. PATCH returns 409 for content changes, but permits a separate audited `enabled` toggle as an emergency operational kill switch. Existing non-registry rule behavior is unchanged. New content is imported as a new version.
3. **Provenance is explicit:** `regulatory`, `checklist`, `integrity`, and `demo` have distinct validation requirements. Backfill legacy demo-only rows as `demo`; generic non-regulatory integrity checks as `integrity`; and ambiguous legacy rows conservatively as `demo`/unverified. An assumption cannot be a source basis. Any required human configuration is explicitly labelled, has no guessed default, and unresolved configuration yields `inconclusive`.
4. **Stable IDs:** use the existing `^[A-Z]{2,6}-\d{3}$` ID pattern, for example `APH-101`, and add a readable `slug` for display.
5. **Evidence is verifiable:** retain the raw quote and its SHA-256. Store start/end character offsets into the exact extracted page text. Normalize only for comparison; never replace the original quote with normalized text.
6. **Page provenance:** record both printed page label (nullable where unavailable) and 1-based PDF page index. Mark OCR-derived pages. Any rule based on OCR-derived text requires an additional independent human comparison against the rendered source page, in addition to the normal two-person approval gate.
7. **Coverage is a sanity check:** report clause/page coverage and require at least 99% normalized non-whitespace page-text coverage to pass the automated coverage gate. Below-threshold coverage blocks progression until explained or corrected; passing is never proof of correctness. Report excluded headers/footers, tables, and OCR limitations explicitly.
8. **Approval is enforceable:** an approved rule needs two distinct reviewers who are not its drafter, approvals bound to both rule and source hashes, and passing evaluator cases recorded with evaluator version. Export fails if any requirement is missing or stale.
9. **Lookup uncertainty stays visible:** each authority/norm entry records source page, cell text, effective dates, and jurisdiction coverage. Missing, unknown, or out-of-coverage entries evaluate as `inconclusive`; the engine never infers a value.
10. **Source material is not committed:** ignore the handbook PDF, amendments, full extracted pages/clauses/tables, and candidates. Commit `SOURCE.md` metadata and hash, tooling/schema/tests, and approved rules containing only permitted short quotes. Confirm reuse terms before committing quotations.
11. **Executable rule types have real evaluators:** `validity_period`, `conditional_document`, and `issuer_authority` each require a `RuleType`, strict parameter schema in `PARAM_SCHEMAS`, evaluator dispatch in `EVALUATORS`, an Alembic enum/check-constraint migration, and tests for pass/issue/inconclusive/not-applicable.
12. **Applicability is not nullable shorthand:** registry applicability must explicitly use `all`, `selected`, or `unknown`. Only explicit `all` maps to backend `application_types=None`; selected maps to its list; unknown remains unresolved and cannot be silently imported as all.
13. **Reference date is reproducible:** use the application's `submitted_at` calendar date by default. An explicit operator-provided `scrutiny_date` remains an override and is labelled as such. If neither exists, do not use the current system date; date-dependent rules return inconclusive. State the selected reference date and its source in findings and reports.
14. **Effective dates have defined behavior:** compare rule effective bounds with the selected reference date. A known out-of-period rule returns `not_applicable` with a note. If either bound is unknown, run the rule and label its effective period as unknown.
15. **Evaluator behavior is versioned:** define `EVALUATOR_VERSION`; record it with test results and registry build metadata. A behavior change requires a version bump and reapproval/retest before export.

## Requirements

| Requirement | Description |
|---|---|
| REQ-RR-001 | Source locking records edition, amendments, publisher, acquisition date, source hash, and reuse/redistribution assessment without committing source PDFs. |
| REQ-RR-002 | Extraction retains verbatim page text, page numbering, OCR method, offsets, and table-cell provenance; quote verification confirms raw text/hash against the source. |
| REQ-RR-003 | Typed registry rules distinguish regulatory, checklist, integrity, and demo provenance; IDs follow the existing pattern and include a slug. |
| REQ-RR-004 | Human approval and evaluator test gates are hash-bound, append-only, and enforced before export. |
| REQ-RR-005 | Only approved rules are imported; managed rules are PATCH-immutable, versioned append-only, and reproducible from snapshot hashes. |
| REQ-RR-006 | Initial extraction fields remain fixed; any later registry-driven extraction changes cache identity through a field-list hash in `PIPELINE_VERSION`. |
| REQ-RR-007 | Authority and norm lookup data includes coverage and effective dates; unknown matches yield `inconclusive`. |
| REQ-RR-008 | API, frontend types where needed, documentation, and tests consistently represent provenance, rule hashes, version history, and lifecycle restrictions. |
| REQ-RR-009 | Three new regulatory rule types have strict parameter schemas, enum/migration support, evaluator dispatch, effective outcomes, and tests. |
| REQ-RR-010 | Existing demo rules `EXP-003` and `FLD-002` are retired without deleting history and are not re-seeded as enabled defaults; verified replacements require handbook approval. |
| REQ-RR-011 | Scrutiny reference date defaults to application `submitted_at`, permits a labelled operator override, never silently falls back to today, and is printed with its source. |
| REQ-RR-012 | Registry applicability explicitly distinguishes all, selected, and unknown; only explicit all maps to backend `None`. |
| REQ-RR-013 | Existing rule rows are backfilled to demo or integrity provenance, with ambiguous rows conservatively labelled demo/unverified. |
| REQ-RR-014 | `EVALUATOR_VERSION` is recorded in test results and approval/export gates enforce evaluator-version consistency. |
| REQ-RR-015 | Findings and PDF reports show provenance from the exact immutable `rule_versions` row, including clause, page, quote, and registry version. |
| REQ-RR-016 | Rule effective-period semantics are enforced during scrutiny: known out-of-period is not applicable; unknown bounds run with an explicit label. |
| REQ-RR-017 | Admins can disable/enable registry-managed rules through an audited toggle, while every other rule-content PATCH remains blocked. |

## Constitution Check

- **Evidence-first and no inference:** Pass. Exact quote, offsets, source page, hash, and OCR marker are required; missing evidence/configuration remains inconclusive.
- **Human review and no automated decision:** Pass. Models may assist triage/drafting only; humans approve. Rules produce preliminary scrutiny outcomes, not approvals or rejections.
- **No unverified regulatory claims:** Pass. Regulatory rules require handbook citations and human verification. Checklist, integrity, and demo content cannot masquerade as handbook rules.
- **Privacy and source handling:** Pass with a source-rights gate. PDFs, full text, and candidates are excluded from Git; do not send handbook contents to an external model unless rights and provider handling have been explicitly cleared.
- **Database and API conventions:** Pass. Alembic migrations, typed schemas, validated parameters, client-safe errors, and documented contracts are required.
- **Compatibility:** Pass with migration gates. Legacy rows get conservative provenance, `EXP-003`/`FLD-002` are retired without erasing history, enum/check constraints are migrated additively, and non-registry rules retain current behavior. No rule-driven extraction/cache invalidation is introduced in the initial release.

## Applied Guidelines

- Existing backend layering: routers validate and call services; parameter validation and rule behavior remain in `rule_catalog.py` and `scrutiny.py`.
- Existing database policy: SQLAlchemy typed models and Alembic migrations; do not edit applied revisions.
- Existing processing policy: bump processing version for behavior changes; evidence must be grounded in stored source text.
- Existing safety policy: missing/ambiguous/unreadable evidence returns `inconclusive`; rule outcomes never determine official decisions.

## Implementation Steps

### Phase 1 — Source handling and extraction

#### Plan 1.1: Establish source and Git boundaries
- **Requirements:** REQ-RR-001
- **Description:** Create the registry structure and a tracked `rules-registry/source/SOURCE.md` template. Add narrowly scoped `.gitignore` rules for source PDFs/amendments, extracted full text/tables, and local candidates. Record source identity, edition, publisher URL, acquisition date, SHA-256, amendments, and reuse assessment. Do not populate handbook-derived content until the user supplies the source path and its edition/terms are checked.

#### Plan 1.2: Extract pages and tables with provenance
- **Requirements:** REQ-RR-002
- **Description:** Implement deterministic `rules-registry/scripts/extract_pdf.py`. Emit one local-only page record per PDF page with 1-based PDF index, printed page label where detected, exact extracted text, extraction method, OCR flag, and source hash. Preserve table cell text with page/cell coordinates. Use OCR only when required and report failure/low-quality cases explicitly; never summarize extracted text.

#### Plan 1.3: Build clause tree and verify quotes
- **Requirements:** REQ-RR-002
- **Description:** Implement `build_clause_tree.py` and `verify_quotes.py`. Store clause text and per-page character offsets into verbatim page text. Verify raw quote/hash, clause/page relationship, page numbers, and normalized matching without mutating stored quotes. Report coverage as a sanity gate with explicit exclusions and OCR warnings; add fixture-PDF tests for boundaries, tables, ligatures, hyphenation, and OCR-derived content.

### Phase 2 — Typed registry and approval controls

#### Plan 2.1: Define registry schemas and provenance validation
- **Requirements:** REQ-RR-003
- **Description:** Add JSON Schemas and Pydantic validation for rules and lookup tables. Use provenance values `regulatory`, `checklist`, `integrity`, and `demo`; reject an unsupported assumption basis. Require exact source, clause, page, quote, offsets, and hashes for regulatory entries; require source-specific citations for checklist entries; do not require a clause for integrity entries. Enforce stable ID format plus `slug`, typed parameters, applicability/conditions/exceptions, effective period, fields needed, outcome templates, ambiguities, and labelled human configuration. Add triage, drafting, and independent-verification prompt templates under `rules-registry/prompts/`; prompts treat handbook text strictly as data, never approve rules, and must not transmit handbook text to an external provider unless rights and provider handling have been cleared.

#### Plan 2.2: Enforce approval and evaluator-test gates
- **Requirements:** REQ-RR-004
- **Description:** Implement registry approval records and rule test-result records bound to `rule_hash`, `source_hash`, reviewer identity, timestamp, and evaluator version. Require two distinct reviewers, neither the drafter; require passing `pass`, `issue`, `inconclusive`, and `not_applicable` cases; require the extra source-page comparison for OCR-derived text. Make validation/export fail explicitly on absent, duplicate, stale, or invalid evidence.

#### Plan 2.3: Validate registry builds and approved output
- **Requirements:** REQ-RR-003, REQ-RR-004
- **Description:** Implement `validate_registry.py` to validate schemas, unique IDs, source/quote hashes, approvals, test results, evaluator version, and provenance. Compute a deterministic registry version from the approved set. Write only approved short-quote rules to the tracked approved registry. Do not export candidate/draft files.

### Phase 3 — Versioned backend integration

#### Plan 3.1: Add provenance and rule-version storage
- **Requirements:** REQ-RR-003, REQ-RR-005
- **Description:** Extend the backend rule representation and create an Alembic migration for registry metadata, an append-only `rule_versions` table, approval records, and evaluator test-result records as required by the implementation design. Preserve existing rows and existing rule behavior. Store the canonical `rule_hash`; enforce immutability of imported versions in service logic and tests.

#### Plan 3.2: Import approved rules and protect managed rules
- **Requirements:** REQ-RR-005
- **Description:** Implement `rules-registry/scripts/export_to_backend.py` and the backend import service/CLI. Validate parameters using backend schemas, import approved rules only, and append a version rather than overwriting an approved version. Keep existing default-rule bootstrap idempotent. Make PATCH return 409 with a client-safe registry-managed immutability error; leave PATCH behavior for non-registry rules unchanged.

#### Plan 3.3: Bind scrutiny snapshots to exact rule content
- **Requirements:** REQ-RR-005
- **Description:** Add `rule_hash` and source clause/page/quote hashes to run snapshots and the rule-set version calculation. Ensure past runs remain reproducible after later imports. Add tests that old snapshots remain unchanged and a change to any rule/source evidence changes the hash.

#### Plan 3.4: Keep initial extraction independent of registry fields
- **Requirements:** REQ-RR-006
- **Description:** Keep `FIELDS_BY_CATEGORY` and the current extraction cache behavior fixed for this release; the registry may validate `fields_needed` against known backend fields but may not alter extraction requests. Document the follow-up requirement: if registry-driven fields are enabled, hash the canonical per-category field list into `PIPELINE_VERSION` and test cache invalidation before rollout.

#### Plan 3.5: Implement registry-backed regulatory evaluators
- **Requirements:** REQ-RR-009
- **Description:** Add `validity_period`, `conditional_document`, and `issuer_authority` to `RuleType` and the matching database CHECK constraint via Alembic. Add strict Pydantic parameter models and `PARAM_SCHEMAS` entries in `rule_catalog.py`; implement and dispatch evaluators in `scrutiny.py`. Use explicit extracted evidence only. Missing/ambiguous required fields or missing reference configuration return `inconclusive`; clear triggers not met return `not_applicable`. Cover each evaluator with pass, issue, inconclusive, and not-applicable tests; do not populate handbook-derived parameters until the source is verified.

#### Plan 3.6: Retire unsupported demo expectations
- **Requirements:** REQ-RR-010, REQ-RR-013
- **Description:** Stop seeding `EXP-003` and `FLD-002` as enabled defaults. Migration disables/marks existing rows retired while retaining historical runs and findings. Do not silently replace either rule with an APH claim; an approved source-backed replacement is imported only after source verification and approval. Update default-rule, scrutiny, workspace, and report tests so demo false positives no longer appear. Backfill existing rows as `demo` or `integrity` from their current explicit flags/status; any ambiguous row is labelled `demo` and unverified.

#### Plan 3.7: Resolve reference dates and applicability explicitly
- **Requirements:** REQ-RR-011, REQ-RR-012
- **Description:** Choose the application's `submitted_at` date as the default scrutiny reference date. Preserve an explicit request date as a labelled operator override. If neither is available, represent the reference date as unavailable and make date-dependent evaluators inconclusive rather than using `date.today()`. Define registry applicability as `all`, `selected`, or `unknown`; translate `all` to backend `application_types=None` only when explicit, translate selected to its list, and reject unresolved unknown applicability from live export.

#### Plan 3.8: Enforce rule effective periods
- **Requirements:** REQ-RR-016
- **Description:** Apply effective-period gating before evaluator dispatch. With a known reference date and known bounds, a date before `from` or after `to` yields `not_applicable` with an explanation. If either bound is unknown, run the evaluator and label the rule's effective period as unknown. If the reference date is unavailable, do not gate by date; run the evaluator, label the effective period as unchecked, and let date-dependent evaluators return `inconclusive`. Add boundary-date, unknown-bound, and missing-reference-date tests.

#### Plan 3.9: Version evaluator behavior
- **Requirements:** REQ-RR-014
- **Description:** Define `EVALUATOR_VERSION` in the scrutiny/evaluator layer and bind test results, approvals, and export validation to it. Behavior changes require a version bump and fresh approval/test evidence. Verify stale evaluator-version evidence blocks export.

#### Plan 3.10: Enforce an audited registry-rule kill switch
- **Requirements:** REQ-RR-017
- **Description:** Allow admin PATCH of registry-managed rules only when the request changes `enabled` and nothing else; audit the old/new state before the same commit. Reject all content changes with 409. Test role access, audit details, rule-content immutability, and snapshot behavior when enabled state changes.

#### Plan 3.11: Persist reference to the exact rule version
- **Requirements:** REQ-RR-005, REQ-RR-015
- **Description:** Associate each evaluation/finding with the immutable `rule_versions` row used by the run (nullable for legacy/non-registry rules). Preserve clause/page/quote metadata in snapshots for historical resilience and include the registry version and reference-date source in the run context.

### Phase 4 — Lookup data, user-facing contract, and release

#### Plan 4.1: Add provenance-aware authority and norm lookups
- **Requirements:** REQ-RR-007
- **Description:** Define authority-directory and norms table schemas with jurisdiction/coverage, effective dates, source page, verbatim cell text, source hash, and verification status. Implement lookup semantics that return unknown/out-of-coverage as `inconclusive`, never as a mismatch or inferred authority. Do not populate values until verified against the supplied source and any applicable amendments.

#### Plan 4.2: Update API, frontend types, and documentation
- **Requirements:** REQ-RR-008, REQ-RR-011, REQ-RR-015, REQ-RR-017
- **Description:** Update API schemas and frontend types/components so findings show clause reference, printed/PDF page, verified short quote, source-verification label, registry version, and reference-date value/source from the exact joined `rule_versions` row. Update the PDF report to print each rule finding's clause/page/quote and registry version, plus reference date/source in the report header. Keep values escaped and distinguish demo/integrity rules. Add an admin enable toggle using the existing confirmation/audit conventions. Update `docs/api-contracts.md`, `docs/data-model.md`, `docs/scrutiny-and-extraction.md`, and `docs/implementation-status.md`.

#### Plan 4.3: Document rule lifecycle and source handling
- **Requirements:** REQ-RR-001, REQ-RR-008, REQ-RR-010, REQ-RR-013
- **Description:** Document source restrictions, conservative legacy provenance backfill, retired demo rules, new evaluator semantics, explicit applicability/date behavior, evaluator versioning, effective-period behavior, and the enabled-only kill switch. Update implementation status only after implementation and test evidence exists.

#### Plan 4.4: Run release gates
- **Requirements:** REQ-RR-001–REQ-RR-017
- **Description:** Run focused registry/backend tests, migration tests on fresh and existing databases, the backend test suite, and frontend typecheck/tests if frontend contracts changed. Confirm Git contains no handbook PDF, full extracted text, or candidate rules; confirm approved quotes satisfy the source-rights gate. Stop release if any approval, evidence, cache, migration, or non-inference gate fails.

## Task Breakdown

### Phase 1 — Source handling and extraction
- [x] T001 [Plan:1.1] Add `rules-registry/README.md`, the `rules-registry/source/SOURCE.md` provenance template, and narrow root `.gitignore` patterns for PDFs, extracted full text/tables, and candidates.
- [ ] T002 [P] [Plan:1.2] Implement `rules-registry/scripts/extract_pdf.py` and fixture tests for page indexing, printed-page metadata, extraction method, OCR flags, table cells, and source hash.
- [ ] T003 [Plan:1.3] Implement `rules-registry/scripts/build_clause_tree.py` and offset/coverage tests using local fixture PDFs.
- [ ] T004 [Plan:1.3] Implement `rules-registry/scripts/verify_quotes.py` and tests for exact raw quotes, hashes, normalized matching, page mapping, OCR flags, and malformed offsets.

### Phase 2 — Typed registry and approval controls
- [ ] T005 [Plan:2.1] Add `rules-registry/schema/rule.schema.json`, `rules-registry/schema/table.schema.json`, typed registry validation for explicit `all`/`selected`/`unknown` applicability and effective dates, and safe prompts under `rules-registry/prompts/`.
- [ ] T006 [Plan:2.2] Add persistent approval and evaluator test-result models/schemas in `backend/app/models/scrutiny.py` and `backend/app/schemas/scrutiny.py`, including source/rule hashes, distinct reviewers, drafter identity, and `EVALUATOR_VERSION`.
- [ ] T007 [Plan:2.2] Add Alembic migration(s) for approval and test-result records; test two-person approval, drafter exclusion, OCR extra-check, stale hashes/versions, and migration preservation.
- [ ] T008 [Plan:2.3] Implement `rules-registry/scripts/validate_registry.py` and tests proving export validation fails for missing approvals, failed/stale tests, invalid evidence, duplicate IDs, unknown applicability, or unverified regulatory sources.

### Phase 3 — Versioned backend integration
- [ ] T009 [Plan:3.1] Add rule provenance metadata and append-only rule-version ORM model(s) in `backend/app/models/scrutiny.py`, including canonical `rule_hash` and source evidence hashes.
- [ ] T010 [Plan:3.1,3.5,3.6,3.7] Add Alembic migration(s) for rule versions, provenance, new `RuleType` values, SQLite CHECK constraints, and nullable reference-date/source fields; backfill legacy rows conservatively and retire existing `EXP-003`/`FLD-002` records without deleting history.
- [x] T011 [Plan:3.2,3.6] Remove `EXP-003` and `FLD-002` from enabled default seeding in `backend/app/services/rule_catalog.py`; update default-rule and regression tests to ensure retired demo expectations do not reappear.
- [ ] T012 [Plan:3.5] Add strict parameter models and `PARAM_SCHEMAS` entries for `validity_period`, `conditional_document`, and `issuer_authority` in `backend/app/services/rule_catalog.py`; test rejected extra/unsupported values and explicit applicability mapping.
- [ ] T013 [Plan:3.5] Implement and dispatch all three evaluator functions in `backend/app/services/scrutiny.py`; test pass, issue, inconclusive, not-applicable, evidence grounding, and absent lookup/configuration cases for each type.
- [x] T014 [Plan:3.7,3.8] Update `backend/app/services/scrutiny.py`, `backend/app/models/scrutiny.py`, and `backend/app/schemas/scrutiny.py` so reference date defaults to application `submitted_at`, explicit request dates are labelled overrides, missing dates do not fall back to today, and effective-period outcomes follow the documented semantics.
- [ ] T015 [Plan:3.9,2.2,2.3] Define `EVALUATOR_VERSION` in `backend/app/services/scrutiny.py`; persist it in registry test results and require matching evaluator version for approvals/export, with behavior-bump and stale-gate tests.
- [x] T016 [Plan:3.10] Update `backend/app/api/v1/scrutiny.py` so admin PATCH on registry-managed rules permits only an `enabled` change, audits it before commit, and returns 409 for content edits; add permission, audit, and immutability tests.
- [ ] T017 [Plan:3.2,3.7] Implement approved-only import in `rules-registry/scripts/export_to_backend.py`, the backend import service/CLI, and idempotence/append-only tests; translate applicability to backend `None` only for explicit registry `all`, rejecting unresolved `unknown`.
- [ ] T018 [Plan:3.3,3.11] Link each registry-backed rule evaluation/finding to its immutable `rule_versions` row and include rule/source hashes, clause/page/quote, registry version, and reference-date source in the run snapshot; test historical reproducibility.
- [ ] T019 [Plan:3.4] Keep extraction requirements fixed in `backend/app/services/extraction.py`; document and test the version-hash requirement before any future registry-driven extraction change.

### Phase 4 — Lookup data, user-facing contract, and release
- [ ] T020 [Plan:4.1] Add authority/norm schemas and lookup evaluators with effective-date and jurisdiction coverage; test missing, unknown, and out-of-coverage entries return inconclusive.
- [ ] T021 [Plan:4.2] Update `frontend/src/types/api.ts` and the findings UI to show verified clause reference, printed/PDF page, short quote, provenance label, registry version, and reference-date value/source from the exact rule version.
- [ ] T022 [Plan:4.2] Update `backend/app/services/report.py` to join findings to exact `rule_versions` and print clause/page/quote and registry version per rule finding, plus reference date/source in the PDF header; add report escaping and provenance tests.
- [x] T023 [Plan:4.2,3.10] Add an admin enable/disable toggle in the rule UI using confirmation and busy-state conventions; test that only the audited enabled toggle is allowed for registry-managed rules.
- [ ] T024 [Plan:4.3] Update `docs/api-contracts.md`, `docs/data-model.md`, `docs/scrutiny-and-extraction.md`, and `docs/implementation-status.md` with implemented evaluator, provenance, dates/applicability, versioning, retired-rule, audit, and citation behavior.
- [ ] T025 [Plan:4.4] Run focused evaluator, registry, API, report, and Alembic tests; run backend suite and applicable frontend typecheck/tests; verify ignored-source boundaries, approved-only export, and all release gates before marking implementation status tested.

## Testing Strategy

- **Application type:** FastAPI backend, local SQLite, React SPA for rule presentation.
- **Critical journeys:** extract a source page and preserve evidence; verify a candidate quote; approve a rule with two eligible reviewers; reject an unapproved/stale export; import an approved version and reproduce it in a scrutiny snapshot; evaluate all three new rule types across their four outcomes; use submission date/labelled override without a system-date fallback; show exact provenance in findings and PDF; reject content PATCH but permit audited enable/disable; return inconclusive for unknown authority/norm coverage.
- **Test data:** small synthetic fixture PDFs only; temporary databases and per-test storage; never use or commit the actual handbook in automated fixtures.
- **Acceptance criteria:**
  - Every regulatory rule has a source hash, clause, both page references where available, exact short quote, quote hash, and verified offsets.
  - The 99% coverage value is reported as a sanity gate and cannot substitute for human verification.
  - No draft enters the backend; no shadow evaluation is implemented in this scope.
  - Export fails unless two distinct non-drafter reviewers and passing evaluator-versioned cases exist for the exact rule/source hashes.
  - Managed rules cannot be edited in place; new versions append; past snapshots remain stable and hash-addressable.
  - `EXP-003` and `FLD-002` are absent from enabled defaults and existing records are retired without deleting historical results.
  - Unknown applicability is not treated as all; only explicit `all` maps to backend `None`.
  - Known out-of-effective-period rules are not applicable; unknown periods run with an explicit label.
  - Findings and PDF reports cite the exact immutable rule version, clause, page, quote, registry version, and reference-date source.
  - Admin enabled-state changes are audited; all other registry rule content edits return 409.
  - Unknown/ambiguous evidence and lookup coverage evaluate as inconclusive.
  - Migrations pass on fresh and existing databases; backend tests pass; frontend typecheck/tests pass when applicable.

## Project Structure (planned)

```text
rules-registry/
  README.md
  source/
    SOURCE.md                         # tracked metadata only
    amendments/                       # local-only PDFs
  extracted/                          # local-only verbatim page/clause/table text
  triage/                             # local working material; no source text copies
  candidates/                         # local-only drafts; never exported
  approved/
    rules.registry.json               # approved rules with permitted short quotes only
  data/
    authority-directory.json           # verified, provenance-bearing entries
    norms.json                         # verified, provenance-bearing entries
  schema/
    rule.schema.json
    table.schema.json
  tests/
    cases/
    fixtures/
  prompts/
    00-build-agent.md
    01-triage.md
    02-draft-rule.md
    03-verify-rule.md
  scripts/
    extract_pdf.py
    build_clause_tree.py
    verify_quotes.py
    validate_registry.py
    export_to_backend.py
backend/
  app/
    models/scrutiny.py                 # provenance, versions, approvals, test records
    schemas/scrutiny.py
    services/rule_catalog.py
    services/scrutiny.py
    api/v1/scrutiny.py
    services/report.py
    db/migrations/versions/            # additive Alembic migration(s)
```

## Requirement Mapping

| REQ ID | Description | Plan Items | Implementation Evidence |
|---|---|---|---|
| REQ-RR-001 | Source lock, provenance, and Git/source-rights boundary | 1.1, 4.4 | `rules-registry/source/SOURCE.md`, root `.gitignore`, source-handling tests |
| REQ-RR-002 | Verbatim extraction, offsets, page/OCR/table provenance, quote verification | 1.2, 1.3 | `rules-registry/scripts/extract_pdf.py`, `build_clause_tree.py`, `verify_quotes.py`, fixture tests |
| REQ-RR-003 | Typed rule schema and explicit provenance classes | 2.1, 2.3, 3.1 | Registry schemas/validator, backend models and parameter validation |
| REQ-RR-004 | Two-person hash-bound approvals and evaluator-versioned tests | 2.2, 2.3 | Approval/test models, `validate_registry.py`, approval and export tests |
| REQ-RR-005 | Approved-only import, append-only versioning, PATCH protection, reproducible snapshots | 3.1, 3.2, 3.3, 3.11 | `rule_versions`, import service/CLI, PATCH 409 tests, run snapshot/hash tests |
| REQ-RR-006 | Safe extraction cache behavior | 3.4 | Fixed extraction field list and documented `PIPELINE_VERSION` hash requirement |
| REQ-RR-007 | Verified lookup tables and inconclusive unknown coverage | 4.1 | Authority/norm schemas, lookup evaluators, unknown/out-of-coverage tests |
| REQ-RR-008 | Consistent API/frontend/docs/tests and release verification | 4.2, 4.3, 4.4 | Backend/frontend contracts, documentation updates, test and migration results |
| REQ-RR-009 | Three new evaluator types with schemas, enum migration, and tests | 3.5 | `RuleType`, `PARAM_SCHEMAS`, evaluator dispatch, migration, four-outcome tests |
| REQ-RR-010 | Retire unsupported demo expectations | 3.6, 4.3 | Seed catalog, migration, default-rule and scrutiny regression tests |
| REQ-RR-011 | Submission-date reference and printed provenance | 3.7, 3.11, 4.2 | Run model/API, evaluator output, finding panel, PDF report |
| REQ-RR-012 | Explicit registry applicability modes | 2.1, 3.7 | Registry schema/import translation and unknown-applicability tests |
| REQ-RR-013 | Conservative provenance backfill | 3.6, 4.3 | Alembic data migration and legacy-row migration tests |
| REQ-RR-014 | Version evaluator behavior and approval evidence | 2.2, 2.3, 3.9 | `EVALUATOR_VERSION`, test-result rows, stale-version export tests |
| REQ-RR-015 | Show exact rule-version citation in findings and report | 3.11, 4.2 | Finding API/UI, PDF report service, citation/render tests |
| REQ-RR-016 | Enforce effective-date semantics | 3.8 | Rule evaluation gating and boundary/unknown-bound tests |
| REQ-RR-017 | Audited enabled-only kill switch | 3.10, 4.2 | PATCH schema/service, audit trail, admin UI and authorization tests |

## Open Prerequisite

The supplied root path resolves to `C:\Users\DELL\OneDrive\Desktop\Regulens-AI\docs\APH Final.pdf`. The file is Git-ignored; its contents have not been inspected for this plan update. Before extraction, record the exact edition, amendments/corrigenda, source hash, and reuse terms. Until source verification is complete, do not populate clauses, page references, quotes, norms, authority entries, or effective dates, and do not treat any examples from the original planning text as verified.
