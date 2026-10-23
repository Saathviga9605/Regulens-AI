# Document Intelligence and Preliminary Scrutiny

ReguLens produces **preliminary, explainable indicators for human review**. It never approves or rejects an
application, never labels a document fraudulent or forged, and never treats a heuristic as proof. Results on the
synthetic demo data say nothing about real-world accuracy.

## Processing pipeline (`PIPELINE_VERSION = p1+cls-1+label_regex_v1`)

1. **Text extraction** (`services/pdf_text.py`, PyMuPDF): per page, 1-based page numbers.
2. **OCR fallback**: a page whose text layer has fewer than `REGULENS_MIN_PAGE_TEXT_CHARS` (default 25)
   non-whitespace characters is an OCR candidate. If Tesseract is available, the page is rendered at
   `REGULENS_OCR_DPI` (capped at 20 MP) and recognised with a per-page timeout. Page statuses: `ok`,
   `insufficient_text` (OCR unavailable/disabled), `ocr_failed`, `ocr_low_text`. Method: `text_layer`, `ocr`, `none`.
3. **Document status**: `completed`; `completed_with_warnings` (some pages unreadable, OCR text used, or repaired
   PDF); `failed` with a safe `failure_code`: `unreadable_pdf`, `encrypted_pdf`, `empty_pdf`, `content_unavailable`,
   `ocr_unavailable` (no usable page and no OCR), `no_readable_text`. OCR being unavailable is **never** reported as a
   successful empty extraction.
4. **Classification** (`services/classification.py`): weighted keyword/heading signals per category; heading
   matches (first 8 non-empty lines of page 1) count double. `confidence`: high (top ≥ 8 and share ≥ 0.70), medium
   (top ≥ 4 and share ≥ 0.55), otherwise `uncertain` (no predicted category). The score is the share of signal
   weight — a heuristic, **not a probability**. The category selected at upload is never changed; disagreement
   produces a warning and a CLS-001 rule result.
5. **Field extraction** (`services/extraction.py`, method `label_regex_v1`): a value is extracted only from an explicit
   label + separator + value on one line (e.g. `Valid Until: 13 March 2029`). The evidence quote is that line and is
   checked to occur in the stored page text (whitespace-normalised only); otherwise the field is `unverified`.
   Statuses: `extracted`, `not_found`, `ambiguous` (several different values, or an ambiguous date), `unverified`.
   Confidence: high (text layer, clean normalisation), medium (OCR page), low (could not normalise).
6. **Caching**: results are keyed by document SHA-256 + pipeline version; a completed result for identical content is
   copied rather than re-extracted. `?force=true` reprocesses. Results cascade-delete with the document.

### Normalisation
- **Dates**: `14 March 2026`, `March 14, 2026`, `14-Mar-2026`, `2026-03-14`, and day-first numeric dates only when
  unambiguous (day > 12 or day = month). `05/06/2026` is kept as written and marked ambiguous.
- **Areas**: sq m / m² / square metres and sq ft / square feet; 1 sq ft = 0.09290304 sq m. Values without a
  recognised unit are kept but not converted and never compared.
- **Names**: case-folded, `&`→`and`, punctuation removed; similarity = max(sequence ratio, token containment).
- **Identifiers**: upper-cased, spaces/dots/hyphens removed, slashes kept.

### Extraction limitations
- Only labelled `Label: value` lines are found; tables, multi-line values, handwriting and unusual wording are missed.
- English only; OCR quality depends on scan quality and the Tesseract install.
- No digital-signature validation, no layout analysis, no visual tamper detection.
- An optional local model could later implement the same field contract; nothing depends on one.

## Rules

Rules are rows in `scrutiny_rules` (defaults in `services/rule_catalog.py`, inserted at startup if missing, never
overwritten). Each has a stable ID, type, validated parameters, severity, enabled flag, source, source reference,
source-verification status, demo-only flag and version. Parameters are validated against a fixed schema per type
(`extra="forbid"`); nothing is executed. Any change increments `version`; each run stores a snapshot.

**No default rule is a verified AICTE requirement.**

| ID | Type | Basis |
|----|------|-------|
| EXP-001…004 | expected_document | **Demo-only, unverified** prototype expectations (EXP-004 applies only to intake-increase / new-course applications) |
| FLD-001…004 | required_field | **Demo-only, unverified** |
| PRC-001 | processing_quality | Integrity check (not regulatory) |
| CLS-001 | classification_consistency | Integrity check |
| CON-001/002 | institution_name_match | Integrity check vs application record (snapshot if frozen) |
| CON-003 | field_consistency (identifier) | Survey numbers across documents and vs record |
| CON-004 | field_consistency (text similarity) | Address vs record |
| CON-005 | area_consistency | Built-up area across documents, tolerance 1 % |
| DAT-001 | date_order | Issue date not after stated validity |
| DAT-002 | expiry_before_scrutiny | Only explicitly stated validity dates; never inferred |
| VER-001 | simulated_issuer_outcome | Reports latest **simulated** issuer check per document |

Outcomes: `pass`, `issue`, `inconclusive`, `not_applicable`. Unusable (ambiguous/unverified) values give
`inconclusive`; a field absent from one document is never a conflict; inconclusive findings are reported one severity
step lower than the rule's severity.

## Anomaly indicators (never conclusions)
`exact_duplicate` (existing SHA-256 duplicate metadata), `content_in_other_application` (count only),
`certificate_number_reused` (same number on different document types or with different issue dates),
`mixed_document_type_signals`, `pdf_incremental_updates` (≥ 3 `%%EOF` markers — common for legitimate edits/signing).
Each has an explanation, evidence, severity and an explicit uncertainty statement.

## Simulated issuer verification
`MockIssuerAdapter` (`services/issuer_verification.py`) looks up **synthetic** reference records
(`issuer_reference_records`) by category + normalised certificate number. Outcomes: `simulated_match`,
`simulated_mismatch`, `simulated_expired`, `simulated_unavailable`, `manual_review` (no reference or no reliable
certificate number — a match is never manufactured), `unsupported`. Every response carries
**“SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY”**. Reference values are never returned. No network access;
no real integration exists. A real adapter would implement the same `IssuerVerificationAdapter` protocol.

## Demo dataset (`python -m app.cli seed`)
All PDFs carry a "FICTIONAL DEMONSTRATION DOCUMENT - NOT A GENUINE CERTIFICATE" banner and metadata.

| Application (seed) | Content | Expected results |
|---|---|---|
| seed-app-01 Deccan Ridge (`REG-EoA-2026-0001` on a fresh DB) | 4 consistent documents | Clean: 0 issues; issuer check on fire certificate → simulated match; occupancy → simulated unavailable |
| seed-app-06 Hooghly (`REG-EoA-2026-0005`) | Fire cert valid until 31 Dec 2025; survey 312 vs 318; area 9,500 sq m vs 86,000 sq ft; exact duplicate; no structural certificate | CON-003, CON-005, DAT-002, EXP-003 issues; duplicate indicator; issuer checks → simulated expired / mismatch |
| seed-app-09 Aravalli (`REG-EoA-2026-0008`) | Image-only scan, resolution uploaded as university NOC, ambiguous date `05/06/2026`, password-protected PDF | PRC-001 issues, CLS-001 mismatch, ambiguous field, inconclusive required-field checks |
