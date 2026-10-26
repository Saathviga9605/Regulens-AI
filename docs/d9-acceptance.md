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

---

## Release check — 2026-10-26 (HEAD `5cd6f71` plus uncommitted release fixes)

### Working database
* Active database: `data/regulens.db` (`REGULENS_DATABASE_URL` in the repo-root `.env`, resolved against the repo root).
  Journal mode `delete` (no WAL); no API, Vite or Python process was running when the backup was taken.
* Revision **0010** (applied automatically by the reload server during D10; no backup existed before that).
* Backup: `data/regulens.pre-release-20261026-190434.backup.db` (573,440 bytes), taken with SQLite's online backup API.
  `PRAGMA integrity_check` = `ok` on both files; same revision (0010), same 29 tables and row counts:
  2 users, 8 institutions, 12 applications, 12 documents, 27 audit events, 1 scrutiny run, 3 findings.

### Fixes made in this check
| Severity | Problem at HEAD | Fix |
|---|---|---|
| BLOCKER | `aph_demo_ruleset.py` referenced `SOURCE_ID`/`SOURCE_VERSION` without defining them (lost when merging D11 over commit `accf8c5`), so the API could not start and every backend test failed at import | Restored the two constants, the profile version `"2"` and the edition title; status/demo flags left exactly as committed |
| BLOCKER | `npm run build` failed (`tsc`: unused `Pill` import after `accf8c5` removed the demo-only pill) | Restored the per-rule **Demo-only** pill and the per-finding **DEMO-ONLY RULE** label (rules are still `is_demo_only=true` in the data) |
| IMPORTANT | `GET /regulatory-source` hard-coded `default: false`; Help, README and the D11 doc said the APH profile is not the default, but commit `58112ed` made `aph_eoa_demo` the default for new runs | Flag now derived from the run request default; copy corrected. The default itself was **not** changed |
| IMPORTANT | `aph-demo-ruleset-status.md` and `implementation-status.md` say "formally approved"; code and tests say formal approval pending | Dated correction note / status corrected |
| MINOR | `design-system.md` still described the removed trust bar | Updated |

Test expectations changed only where a committed functional change requires it: the APH profile-selector banner
(removed in `accf8c5`), the endpoint `default` flag, and the smoke script, which now selects the production profile
for its survey-conflict step.

### Processing-status 404s
`GET /documents/{id}/processing` returns `404 not_processed` for an uploaded but unprocessed document. This is
documented in `api-contracts.md` and handled in `DocumentAnalysis.loadProcessing` as a normal "not processed yet"
state: one request, no error shown, no retry. The browser logs any non-2xx response, which is where the console
lines came from. **Correct by design; not changed.** Regression tests: processed → 200, unprocessed → 404
`not_processed`, unknown id → 404 `not_found`, unauthenticated → 401 (`test_processing.py`), and the UI makes
exactly one request with no alert (`scrutiny.test.tsx`).

### Regulatory source
`python -m app.cli aph-source --verify <pdf>` against the copy downloaded on 2026-10-25: `status: verified`
(SHA-256 matches, 231 pages, page label "81" found, all 4 quotations found, quote hashes OK), exit 0. The
manifest is unchanged; R01, R02 and R08 remain `PARTIALLY_VERIFIED`; Clause 7.17 remains unresolved; no rule is
`SOURCE_VERIFIED`. The PDF is not in the repository: without a local copy only the manifest and quote hashes can
be checked.

### Test results
| Check | Result |
|---|---|
| Backend `pytest` (with `APH_PDF` set) | 313 tests: 312 passed, 1 skipped (Tesseract not installed), 0 failed; exit 0 |
| Frontend `vitest run` | 9 files, 102 passed; exit 0 |
| `tsc -b --noEmit` / `npm run build` | exit 0 / exit 0 |
| `npm audit` | 0 vulnerabilities |
| `pip-audit -r requirements.lock.txt` | first run: 1 advisory, pytest 8.4.2 (PYSEC-2026-1845 / CVE-2025-71176, UNIX `/tmp` only, dev extra). Resolved in the final cleanup (below) |
| `pip check` | rapidocr-onnxruntime declares `opencv-python`; `opencv-python-headless` is installed instead (intentional `--no-deps` install) |
| `reuse-eval` (OCR on) | identical to `docs/evaluation/reuse-d10/metrics.csv` (80 rows, 0 differences, latency ignored) |

### Browser acceptance (Edge, disposable DB, API :8090, web :5210)
All 19 steps passed: sign in; existing applications; native PDF (text layer); scanned PDF (RapidOCR, page score
0.91); PNG (OCR, 6 fields); `.txt`, truncated PNG and fake PDF rejected and not stored; fields with OCR score
and evidence box; APH citation with handbook edition, clause and quote; Regulatory source page (hash,
3 × partially verified, Clause 7.17 unresolved); issuer checks SIMULATED and NOT_CONNECTED; transformed copy →
MATCH_CONFIRMED_FOR_REVIEW with traceable explanation; same-template → NOT_MATCHED; altered and altered scan →
CANDIDATE; poor scan produced no pair; reviewer gets restricted alerts and 403 on pair endpoints, cross-case reviewer
sees 40 pairs; escalation persists after reload; report PDF downloaded; evaluation run in the browser (276 s) and CSV
exported; audit entries for every action; no horizontal overflow at 360–1920 px. The smoke script also passed.
Only console errors: the deliberate bad-password 401 and the two deliberate 415 upload rejections.

### Open items
* **IMPORTANT (team decision A, open):** see "Team decisions" below.
* **IMPORTANT (team decision B, open):** see "Team decisions" below.
* ~~MINOR: `/system/info` capability text~~ and ~~MINOR: pytest advisory~~: resolved in the final cleanup.
* **EXTERNAL:** Tesseract not installed (RapidOCR used); real photographed captures need a physical device;
  live issuer verification needs an authorised service; amendments/corrigenda to the handbook not checked.

### Reproduce
```powershell
cd backend; $env:APH_PDF="<path to handbook PDF>"; .\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m app.cli aph-source --verify "<path to handbook PDF>"
.\.venv\Scripts\python.exe -m app.cli reuse-eval --out <new folder>   # compare with docs\evaluation\reuse-d10
cd ..\frontend; npx vitest run; npx tsc -b --noEmit; npm run build; npm audit
# browser: disposable DB → migrate, seed, reuse-fixtures --load, create-user senior.reviewer, grant-cross-case;
# start the API and web app on spare ports, then:
$env:SMOKE_ALLOW_WRITES="1"; $env:SMOKE_BASE_URL="http://127.0.0.1:<web>"; $env:SMOKE_API_URL="http://127.0.0.1:<api>/api/v1"; npm run smoke
```

## Final cleanup — 2026-10-26

* `/system/info` `implemented_capabilities` / `planned_capabilities` rewritten to match the code: features built in
  D2–D11 are listed as implemented; "planned" now holds only what is not done (live issuer verification, evaluation
  on real photographs, a formal approval record for the APH rules). Field names unchanged. The lists are not shown
  in the UI. Test: `test_capability_text_matches_implementation`.
* pytest 8.4.2 → **9.0.3** (dev extra `pytest>=9.0.3,<10`, lockfile pin). Advisory PYSEC-2026-1845 /
  CVE-2025-71176 concerns predictable `/tmp/pytest-of-{user}` directories on UNIX; this project runs on Windows and
  pytest is test-only, so exposure was low, but the update was compatible: the full suite passed under 9.0.3 in an
  isolated venv built from the lockfile before the pin was changed. `pip-audit` on `requirements.lock.txt` and
  `requirements-ocr.txt` now reports no known vulnerabilities.

### Team decisions (not made on the team's behalf)

**A. Default ruleset for new runs.** Code default: `aph_eoa_demo` (commit `58112ed`), consistent in the API
(`RunRequest`), the service and the UI selector; `/regulatory-source` reports `default: true`. Practical effect:
on the seeded applications (no submission dates) APH runs give inconclusive "submission date unavailable"
findings; the survey-number conflict and other consistency findings appear only when **production** is chosen in
"Ruleset profile for the next run". To decide: which profile a fresh run should use in the demonstration. Changing
it is a one-line default in three places plus test and copy updates.

**B. Formal approval of the APH rules.** Commit `accf8c5`'s message and docs say "formally approved"; the code
(`5cd6f71` and this cleanup) keeps `source_verification_status=unverified`, `is_demo_only=true`, classification
`PARTIALLY_VERIFIED` and "formal approval pending". A commit message is not an approval record. To resolve, the
team needs: the approving person/body and date; the approved rule IDs and versions (R01/R02/R08 v2, profile v2);
sign-off on each documented interpretation (validity date for R01, application types and the unresolved
Clause 7.17 for R02, reference date for R08); and where the record is kept. Only then change the flags, with a
new rule version and tests. Even then the classification stays `PARTIALLY_VERIFIED` while interpretations remain;
`SOURCE_VERIFIED` needs a rule whose logic restates the quotation without interpretation.

**What the handbook check proves.** `aph-source --verify` matching the pinned SHA-256 and finding the expected
quotations and page label shows that the local file is the exact artifact pinned on 2026-10-25 and that the cited
text is in it. It does not show that no later amendment or corrigendum exists, that ReguLens' interpretations are
correct, or that any rule is approved.
