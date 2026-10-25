# Deliverable 9 — acceptance, status alignment and release hardening

Scope authority: the Project Bible v2.0 / v3.0 amendments are **not present in the repository**; the Deliverable 9
brief was used as the authoritative statement of their requirements.

Starting state (verified 2026-10-25): `main` at `eb3a0b9`, clean worktree; backend 278 passed + 1 skipped, frontend
95 passed; working database `data/regulens.db` at Alembic revision **0004** (read-only check — never modified).

## Acceptance checklist

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | A0 / A1 / A4 on identical labelled pairs, same splits | VERIFIED | `reuse_eval.evaluate`; `test_arms_use_the_same_pairs_and_report_traceability`; `docs/evaluation/reuse-d9/` |
| 1a | A1 threshold dev-only, frozen; history of held-out inspection documented | VERIFIED | A1 ≤ 0 selected on `dev` in D7; split notes in every export |
| 1b | TP/FP/TN/FN, precision, recall, hard-negative FP rate with denominators; inconclusive separate | VERIFIED | `metrics.json`/`summary.md` (inconclusive and hard-negative CANDIDATE counts per split) |
| 1c | By transformation type and quality; pipeline version, OCR availability, thresholds, fixture manifest, timestamp | VERIFIED | `by_transform`, `by_quality`, `config`, `environment`, `fixture_manifest` (63 docs, SHA-256), `evaluated_at` |
| 1d | Synthetic ground truth separate from production records | VERIFIED | labels live only in `reuse_dataset.py`; `case_pairs.ground_truth_label` CHECK (fixtures only); test asserts production scans never set it |
| 2 | Real printed-and-phone-photographed pairs | **BLOCKED** | no camera or printer available. Workflow built: `python -m app.cli capture-kit --out DIR`, manifest validation (`physical_capture.py`) rejects simulated images and missing files; eval reports status `BLOCKED` |
| 2a | Simulated photographs clearly distinguished | VERIFIED | recipes say "simulated photograph"; manifest loader refuses `kind: simulated` |
| 3 | Campus-photo experiment (positive crop/colour shift; similar-building hard negative) | VERIFIED (synthetic) | `image_reuse.py`; campus dev 6/6 correct; campus held-out TP2 FP0 TN3 FN1; separate section in exports and UI |
| 4 | Altered-document analysis: five controlled case types, before/after on dev, held-out evaluation | VERIFIED | `dev_alt`/`heldout_alt` suites; `test_alteration_suite_outcomes[dev_alt|heldout_alt]`; v3→v4 comparison below |
| 5 | Six source-verification labels; separate from rule outcome, evidence state, reviewer disposition, reuse outcome; source type LIVE/SIMULATED/NOT_CONNECTED | VERIFIED | `IssuerSourceStatus`, `SourceType`, `services/source_status.py`, migration 0009, API fields, UI, report column; `test_d9.py` |
| 6 | Cross-case access control and audit | VERIFIED (unchanged, strengthened) | existing D7 tests + new leak tests on error responses, documents list, evaluation endpoint, exports; browser: 3/3 direct calls → 403, audited |
| 7 | Migration safety | VERIFIED on disposable copies | fresh → 0009; copy of working DB 0004 → 0009 (counts preserved); 0009 → 0008 → 0009; backfill test for all six outcomes |
| 7a | Working database migrated | **Requires user action** | still at 0004; see "Migrating your working database" |
| 8 | Optional public EoA extraction check | OMITTED | would require downloading and annotating third-party PDFs and handling personal data; not needed for core scope |
| 9 | Frontend: status dimensions, altered fields without fraud language, low-confidence/inconclusive states, OCR/simulated transparency, evaluation counts, campus separate | VERIFIED | comparison-page status legend, explanation/fusion, document-analysis source status + type badge, evaluation panel sections; `ai.test.tsx`, `scrutiny.test.tsx` |
| 10 | Full regression, build, audit, browser acceptance, smoke | VERIFIED | see "Verification" |

## Source-verification status mapping

| Dimension | Values | Where |
|---|---|---|
| Rule outcome | rule evaluation outcomes (pass/fail/inconclusive …) | scrutiny runs |
| Evidence state | extracted / not found / ambiguous / unverified | extracted fields |
| **Source-verification status** | **Verified, Mismatch detected, Expired, Verification pending, Source unavailable, Manual review required** | `verification_attempts.source_status` |
| Source type | LIVE (never produced — no live integration), SIMULATED, NOT_CONNECTED | `verification_attempts.source_type` |
| Reviewer disposition | finding review states; pair: not reviewed / confirmed for further review / dismissed / escalated | review actions |
| Cross-case reuse outcome | MATCH_CONFIRMED_FOR_REVIEW, CANDIDATE, NOT_MATCHED, INCONCLUSIVE | case pairs |

Adapter outcome → status: simulated_match → Verified; simulated_mismatch → Mismatch detected; simulated_expired →
Expired; simulated_unavailable → Source unavailable; manual_review → Manual review required; unsupported (no source
for the document type) → Manual review required with source type NOT_CONNECTED; no attempt yet → Verification
pending. The existing rule-provenance enum `SourceVerificationStatus` (verified/unverified/not applicable for a
rule's regulatory source) is a different concept and is unchanged.

## Altered-document analysis (cascade v4, thresholds `reuse_thr_v4`)

Change: with ≥ 2 conflicting critical fields, the pair is kept as `CANDIDATE` when geometry is verified, **every**
difference region lies on the line of a critical field (field box extended to the right edge of its line, because a
replacement value may be longer), and ≥ 1 critical field still agrees. Address is now a compared field
(`fieldcmp_v3`). Rationale text says "possible alteration of a reused document, or a different certificate issued on
the same template. Requires review; not a finding of fraud." Nothing is ever confirmed by this rule.

Before/after on development splits (RapidOCR on; v3 behaviour = `localized_alteration_rule=False`):

| Case | dev_alt v3 | dev_alt v4 |
|---|---|---|
| benign rescaled copy | confirmed | confirmed |
| one altered field | candidate | candidate |
| two altered fields (name + address) | not matched | **candidate** |
| three altered fields (number + dates) | not matched | **candidate** |
| scanned two-field alteration (OCR) | not matched | **candidate** |
| same template, different document (all fields differ) | not matched | not matched |
| poor scan | inconclusive | inconclusive |

Also changed on dev: `dev_p07` (same institution, earlier certificate — labelled distinct) not matched → candidate:
by evidence it is indistinguishable from a number-and-date alteration, so human review is the honest outcome.

Held-out (`heldout_alt`, evaluated once after v4 was frozen): the 4 altered pairs → 4 candidate, 0 confirmed; the
same-template different document → not matched; benign copy → confirmed; poor scan → inconclusive. Without OCR the
scanned alteration falls to not matched (3/4 candidate). Remaining miss: `ho_p13` (two dates differing by one year
digit, in the previously inspected held-out set) stays not matched — the residual map finds no differing region to
localise.

## Evaluation results (`docs/evaluation/reuse-d9/`, `reuse_ds_v3`, OCR = RapidOCR)

A4 positive = `MATCH_CONFIRMED_FOR_REVIEW`; altered pairs excluded from binary counts and reported above. Synthetic
prototype benchmark — no statistical significance.

| Split (binary pairs) | A0 TP/FP/TN/FN | A1 TP/FP/TN/FN | A4 TP/FP/TN/FN | A4 inconclusive | Hard-neg FP A1 / A4 | Hard-neg CANDIDATE (A4) |
|---|---|---|---|---|---|---|
| dev (11) | 1/0/6/4 | 3/0/6/2 | 5/0/6/0 | 1 | 0/5 · 0/5 | 1 |
| dev2 (6) | 0/0/2/4 | 0/0/2/4 | 3/0/2/1 | 1 | 0/2 · 0/2 | 0 |
| dev_alt (3) | 0/0/1/2 | 1/0/1/1 | 1/0/1/1 | 1 | 0/1 · 0/1 | 0 |
| heldout (15, inspected) | 1/0/8/6 | 3/2/6/4 | 7/0/8/0 | 1 | 2/7 · 0/7 | 2 |
| heldout2 (12, inspected in D8) | 1/0/6/5 | 3/1/5/3 | 5/0/6/1 | 2 | 1/5 · 0/5 | 1 |
| heldout_alt (3, fresh) | 0/0/1/2 | 0/1/0/2 | 1/0/1/1 | 1 | 1/1 · 0/1 | 0 |

Without OCR (`reuse-d9-no-ocr/`): A4 recall dev 3/5, dev2 0/4, heldout 4/7, heldout2 2/6, alteration suites 1/2;
0 false positives everywhere. Field exact match with OCR: institution 45/56, certificate number 52/56, issue date 35/40
(without OCR 38/56, 38/56, 26/40). Evidence traceability 396/396 (270/270 without OCR). All A4 FNs are poor scans
(reported inconclusive). D7/D8 exports are unchanged in `reuse-d7*`, `reuse-d8*`.

Campus experiment (synthetic facades; separate): campus_dev TP3 FP0 TN3 FN0; campus_heldout TP2 FP0 TN3 FN1 (miss:
15 % crop, 64 inliers < 90). pHash distances overlapped between same-image and different-building pairs, so the
indicator relies on geometry. The indicator is advisory only.

## Migrating your working database

The API runs migrations automatically at start-up. Your `data/regulens.db` is at 0004, so the next server start
would apply 0005–0009. Back it up first (PowerShell, from the repository root, with the server stopped):

```powershell
Copy-Item data\regulens.db ("data\regulens.backup-" + (Get-Date -Format yyyyMMdd-HHmmss) + ".db")
cd backend; .\.venv\Scripts\Activate.ps1
python -c "import sqlite3;print(sqlite3.connect('file:../data/regulens.db?mode=ro',uri=True).execute('select version_num from alembic_version').fetchall())"
python -m app.cli migrate          # applies 0005 … 0009; prints "Database schema is up to date."
python -m app.cli seed-summary     # confirm counts are unchanged
```

All of 0005–0009 were verified on a copy of this database (counts preserved). Restore = copy the backup back.

## Clean-start demo (disposable environment)

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
$env:REGULENS_DATABASE_URL = "sqlite:///$env:TEMP/regulens-demo.db"; $env:REGULENS_DOCUMENT_STORAGE_DIR = "$env:TEMP/regulens-demo-docs"
$env:REGULENS_OCR_ENGINE = "rapidocr"   # after pip install -r requirements-ocr.txt; pip install --no-deps rapidocr-onnxruntime==1.2.3
python -m app.cli seed
python -m app.cli reuse-fixtures --load
python -m app.cli grant-cross-case --username demo.reviewer
python -m uvicorn app.main:app --port 8000      # frontend: cd ..\frontend; npm run dev
python -m app.cli reuse-eval --out ..\docs\evaluation\reuse-d9
python -m app.cli reuse-eval --no-ocr --out ..\docs\evaluation\reuse-d9-no-ocr
python -m app.cli capture-kit --out ..\capture-kit   # printable sources for real photo captures
```

## Demo-readiness checklist

| Step | Status (browser, Edge, disposable DB, 2026-10-25) |
|---|---|
| Start app; load synthetic fixtures | done |
| Process a text PDF and an OCR scan | done (text layer; RapidOCR score 0.91) |
| Transformed-copy comparison | MATCH_CONFIRMED_FOR_REVIEW |
| Same-template negative | NOT_MATCHED |
| Altered critical fields | CANDIDATE (text PDF and OCR scan); rule names the differing fields; no fraud language |
| Poor-quality scan | never paired / never confirmed |
| Source-verification statuses | Verified (SIMULATED); Manual review required (NOT_CONNECTED) |
| Unauthorised / authorised cross-case access | 403 ×3 for reviewer; senior views details; audited |
| Disposition + report | escalation persisted after reload; preliminary report PDF downloaded |
| Evaluation + export | ran in browser (355 s), CSV exported |
| Existing smoke workflow | passed |

## Known limitations and next actions

* Real phone photographs: BLOCKED until someone prints and photographs the capture kit (≈ 30 minutes).
* Optional public EoA extraction check: omitted.
* Two-field alterations with sub-glyph changes (`ho_p13`) are missed; same-issuer later certificates surface as
  candidates (by design, for review).
* Campus experiment is synthetic; real photographs of buildings may differ (perspective, season, occlusion).
* The working database still needs the backed-up migration above.
* The Project Bible documents should be added to the repository so future scope checks can cite them directly.
