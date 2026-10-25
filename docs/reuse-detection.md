# Cross-case document reuse detection (Deliverable 7)

ReguLens detects **potential reuse of the same underlying document across different application cases** and
explains the evidence to an authorised reviewer. A similarity score, a matching outcome or a reviewer's
confirmation is **not** proof of reuse, forgery, fraud or misconduct, and nothing here establishes authenticity.

## Matching cascade

Code: `backend/app/services/reuse_engine.py` (pure, no database), `reuse_visual.py`, persistence in `reuse.py`.
Every stage stores its raw metric, method and version in `match_evidence`; no single opaque score is stored alone.

| Stage | Method (version) | What it reports | Role |
|---|---|---|---|
| L0 exact | SHA-256 | `equal` | Byte identity only |
| L1 text | `txtnorm_v1`: NFKC, zero-width/soft-hyphen removal, casefold, whitespace runs → one space. Nothing else removed (identifiers, digits, punctuation kept). Character 5-gram shingles | Jaccard, containment, shingle counts | Retrieval (Jaccard ≥ 0.45) and corroboration. Texts under 60 characters, failed or unprocessed are *unavailable*, never a match |
| L2 visual | `phash_dct_v1`: page rendered greyscale at 36 dpi, cropped to its content box, 32×32 area resize, 2-D DCT, 8×8 block thresholded at median; hashes for 0/90/180/270° | Best Hamming distance (64-bit), page pair, rotation | Retrieval only (distance ≤ 12). Near-blank pages are skipped |
| L3 geometry | `orb_ransac_v1`: OpenCV ORB (3000 features) at 150 dpi, kNN + ratio test 0.75, RANSAC homography (5 px). If the scale differs by >6 %, page B is re-rendered at the matching resolution and re-estimated | Keypoints, tentative matches, inliers, inlier ratio, coverage of A's content cells (6×6 grid, ≥3 % ink), transform, status | Verified when inliers ≥ 40, ratio ≥ 0.25, coverage ≥ 0.52 |
| L3 residual | `aligned_intensity_residual_v1`: ECC sub-pixel refinement, percentile normalisation, Gaussian blur σ 2, |A−B| > 70, connected regions ≥ 60 px | Localized difference regions with boxes in A's frame | Distinguishes the same content from the same template with changed details |
| Fields | `fieldcmp_v1` over institution name, certificate number, issue date, NOC/structural reference, survey number, valid until, trust name, resolution date | Per field: raw values, normalised values, page, quote, agree / conflict / inconclusive, explanation | A field is compared only with a valid source pointer (status `extracted` and the quote found in that page's stored text). Missing, ambiguous or unreadable → inconclusive, never conflict |

OpenCV (`opencv-python-headless`) ran in every reported result. If it is missing, L3 reports `unavailable` and is
never replaced by a pHash result. OCR (Tesseract) was **not** installed on the verification machine, so image-only
pages had no text or fields.

## Outcomes and decision rules (`reuse_cascade_v2`)

| Outcome | Meaning |
|---|---|
| `MATCH_CONFIRMED_FOR_REVIEW` | Byte identity, or strong text similarity (≥ 0.85) with ≥ 2 agreeing grounded fields, or aligned pages with no localized differences plus text or field corroboration, and no conflicting critical field |
| `CANDIDATE` | Some evidence (aligned pages without text to corroborate, one conflicting field on otherwise shared content, aligned pages with a few local differences) |
| `NOT_MATCHED` | Examined and not shared content: unrelated readable text, several conflicting fields on a shared template, or layout-only alignment with more than 4 difference regions |
| `INCONCLUSIVE` | Neither text nor page images could be compared |

These are matching outcomes, not compliance decisions. A shared blank template, logo, border, stamp or a single
pHash threshold can never produce `MATCH_CONFIRMED_FOR_REVIEW`.

## Threshold selection and versioning

* Thresholds live in `ReuseConfig` (`reuse_thr_vN`) and every evaluation stores the full configuration snapshot.
  Pairs are keyed by document ids + SHA-256s + pipeline version + config version: reruns on unchanged inputs reuse
  the stored pair; a new document, algorithm or configuration produces a new, separately stored evaluation, and
  earlier ones are never rewritten (`include_superseded=true` lists them).
* **v1** (`reuse_thr_v1`): coverage 0.52, pHash retrieval 12, residual parameters and A1 threshold 0 were selected
  on the **dev split only** (scratch sweeps over dev pairs), frozen, then the held-out split was evaluated once.
* **v2** (`reuse_thr_v2`, engine `reuse_cascade_v2`): browser integration testing on the seed demo documents (not
  part of the evaluation set) showed false `CANDIDATE`s between unrelated plain-layout documents. Two rule fixes:
  unrelated readable text is checked before the single-conflict "possible alteration" rule, and verified geometry
  with more than `max_diff_regions_shared = 4` regions counts as layout-only. The value 4 was taken from dev values
  only (positives/alterations 0–1 regions, same-template negatives 7–17). Both splits were re-run: every metric is
  identical to v1 (`docs/evaluation/reuse-d7-v1/` vs `docs/evaluation/reuse-d7/`); on the seed scan, false candidates
  for case A fell from 8 to 0. Because this change came after the held-out run, the held-out set is no longer
  strictly untouched for v2; it is reported as such.

## Cross-case access control

| Who | Can |
|---|---|
| Any signed-in reviewer | Start a scan for an application; see scan counts; see **restricted alerts**: own document, outcome, review state — never the linked application, institution, filename, document id, text, fields, metrics or images |
| `cross_case_reviewer` (per-user permission, granted by an administrator) | List pairs, open pair detail and evidence, view page images, record and read dispositions |
| Administrator | Grant/revoke the permission for **other** users (self-change refused); run/export evaluations. The admin role alone does **not** grant pair details |

Enforcement is server-side: every pair route is on a router whose dependency requires the permission
(`require_cross_case_reviewer`). In-app alerts (visible to all staff) name only the local document.

**Limitation:** ReguLens still has no per-application assignment; every reviewer can open every application
directly. The protected asset is the cross-case *linkage* and its evidence — the restricted views never reveal
which case or document matched.

## Audit

`cross_case.scan_completed`/`scan_failed`, `cross_case.pair_viewed`, `cross_case.page_image_viewed`,
`cross_case.review_action`, `cross_case.access_denied` (outcome `denied`), `cross_case.evaluation_run`,
`user.permission_changed`, `reuse_fixtures.reset`. Each carries actor, UTC time, request id, pair id and action.
No document text, field values, filenames of the linked case or reviewer notes are written to audit details.

## Reviewer dispositions

`confirm_candidate` (needs further review — not a misconduct finding), `dismiss`, `escalate` (each needs a reason
≥ 10 characters) and `note`. Stored append-only in `case_pair_review_actions` with optimistic concurrency
(`expected_version`); system evidence is never modified. A disposition belongs to the evaluation version it was
made on; after a configuration change the re-evaluated pair must be reviewed again.

## Synthetic dataset (`reuse_ds_v1`)

`backend/app/services/reuse_dataset.py`, deterministic (byte-identical builds, digest `c579ee4e0209f12c`), all
documents fictional and bannered. 28 documents / 28 fictional cases; pair-level labels.

| Split | Pairs | reuse | altered | distinct | hard negatives |
|---|---|---|---|---|---|
| dev | 12 | 5 | 1 | 6 | 5 |
| heldout | 16 | 7 | 1 | 8 | 7 |

Covered: exact duplicate across cases; metadata-only change; vector rescale/rotation/crop (text layer kept);
scan-like raster copies (rotation, scale, crop, brightness/contrast, noise, blur, JPEG; no text layer); same
template with a different institution; same issuer layout with different number/dates; similar seal/border with
unrelated body; two documents of the same institution; controlled field alterations; near-blank unreadable pages.
Dev and held-out use different fictional issuers, institutions and documents.

**Not implemented:** printed-and-phone-photographed pairs (no capture equipment used) and campus-photo pairs.

Hero scenarios: `ho_p02` (rescaled copy submitted by another institution) and `ho_p08` (same template, different
institution). `python -m app.cli reuse-fixtures --load` loads them (plus a raster copy) as four fictional cases;
`--reset --confirm-reset` removes only those cases (development/test only).

## Evaluation (A0 / A1 / A4) — measured results

`python -m app.cli reuse-eval --out DIR` (no network, no database). Same labelled pairs for all arms. Binary counts
use `reuse` vs `distinct`; `altered` pairs are listed separately; for A4 only `MATCH_CONFIRMED_FOR_REVIEW` counts as
positive. No statistical significance is claimed from 15 pairs.

| Held-out (15 binary pairs) | TP | FP | TN | FN | Precision | Recall | Hard-neg FP |
|---|---|---|---|---|---|---|---|
| A0 exact hash | 1 | 0 | 8 | 6 | 1/1 | 1/7 | 0/7 |
| A1 pHash ≤ 0 | 3 | 2 | 6 | 4 | 3/5 | 3/7 | 2/7 |
| A4 full cascade | 4 | 0 | 8 | 3 | 4/4 | 4/7 | 0/7 |

Dev (11 binary pairs): A0 1/1 precision, 1/5 recall; A1 3/3, 3/5; A4 3/3, 3/5; hard-negative FP 0/5 for all.
A4 held-out outcomes: 4 confirmed, 4 candidate, 7 not matched, 1 inconclusive. Critical-field exact match:
institution name, certificate number and issue date each 18/23 (the 5 misses are image-only copies without OCR).
Evidence traceability: 90/90 surfaced source references valid. Latency: A4 ≈ 9.4 s for 16 held-out pairs incl.
text extraction (≈ 0.6 s/pair); A1 ≈ 0.16 s. Full exports: `docs/evaluation/reuse-d7/`.

## Known failure cases

* Raster copies without OCR stay `CANDIDATE` (3 held-out FNs): pages align with no differences, but no text or
  fields can corroborate.
* An alteration that changes **two** fields (`ho_p13`, both dates) is `NOT_MATCHED` — indistinguishable by rule from
  a different certificate on the same template.
* A raster copy compared with a same-issuer negative can be `CANDIDATE` (`ho_p16`, 3 difference regions).
* Geometric verification uses one best page pair; multi-page reuse of a different page is only seen via text.
* Retrieval compares against at most 500 most recent documents per scan; scans run synchronously.
