# Cross-case reuse evaluation (reuse_eval_v3)

Dataset `reuse_ds_v3` (digest `86442db97cdd0875`), config `reuse_thr_v4`, pipeline `reuse_cascade_v4+txtnorm_v2+phash_dct_v2+orb_ransac_v1+fieldcmp_v3+fusion_v1`. A1 threshold: pHash distance ≤ 0 (dev-selected).
OCR available: False; OpenCV: 5.0.0.

Synthetic data only; tiny sample — no statistical significance is claimed.

## dev

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 6 | 4 | 1.00 (1/1) | 0.20 (1/5) | 0/5 | 0.0 |
| A1 | 3 | 0 | 6 | 2 | 1.00 (3/3) | 0.60 (3/5) | 0/5 | 227.1 |
| A4 | 3 | 0 | 6 | 2 | 1.00 (3/3) | 0.60 (3/5) | 0/5 | 9784.5 |
## dev2

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 0 | 0 | 2 | 4 | n/a (0/0) | 0.00 (0/4) | 0/2 | 0.0 |
| A1 | 0 | 0 | 2 | 4 | n/a (0/0) | 0.00 (0/4) | 0/2 | 92.3 |
| A4 | 0 | 0 | 2 | 4 | n/a (0/0) | 0.00 (0/4) | 0/2 | 11468.7 |
## dev_alt

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 0 | 0 | 1 | 2 | n/a (0/0) | 0.00 (0/2) | 0/1 | 0.0 |
| A1 | 1 | 0 | 1 | 1 | 1.00 (1/1) | 0.50 (1/2) | 0/1 | 107.6 |
| A4 | 1 | 0 | 1 | 1 | 1.00 (1/1) | 0.50 (1/2) | 0/1 | 4093.4 |
## heldout

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 8 | 6 | 1.00 (1/1) | 0.14 (1/7) | 0/7 | 0.0 |
| A1 | 3 | 2 | 6 | 4 | 0.60 (3/5) | 0.43 (3/7) | 2/7 | 210.2 |
| A4 | 4 | 0 | 8 | 3 | 1.00 (4/4) | 0.57 (4/7) | 0/7 | 10824.2 |
## heldout2

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 6 | 5 | 1.00 (1/1) | 0.17 (1/6) | 0/5 | 0.0 |
| A1 | 3 | 1 | 5 | 3 | 0.75 (3/4) | 0.50 (3/6) | 1/5 | 197.0 |
| A4 | 2 | 0 | 6 | 4 | 1.00 (2/2) | 0.33 (2/6) | 0/5 | 11998.7 |
## heldout_alt

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 0 | 0 | 1 | 2 | n/a (0/0) | 0.00 (0/2) | 0/1 | 0.0 |
| A1 | 0 | 1 | 0 | 2 | 0.00 (0/1) | 0.00 (0/2) | 1/1 | 109.2 |
| A4 | 1 | 0 | 1 | 1 | 1.00 (1/1) | 0.50 (1/2) | 0/1 | 4324.3 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 1, CANDIDATE 3, NOT_MATCHED 2, INCONCLUSIVE 1. Hard negatives surfaced as CANDIDATE (review, not confirmed): 0.

## Critical-field exact match

| Field | Exact / evaluated |
|---|---|
| institution_name | 38/56 |
| certificate_number | 38/56 |
| issue_date | 26/40 |

Evidence traceability (A4): 270/270 source references valid.

## Altered pairs (reported separately)

- dev_p10 (critical-field alteration): A0 False, A1 True, A4 CANDIDATE
- ho_p13 (critical-field alteration (dates)): A0 False, A1 True, A4 NOT_MATCHED
- h2_p11 (certificate number changed): A0 False, A1 True, A4 CANDIDATE
- dev_alt_p2 (one altered critical field): A0 False, A1 True, A4 CANDIDATE
- dev_alt_p3 (two altered fields (identity)): A0 False, A1 True, A4 CANDIDATE
- dev_alt_p4 (three altered fields (number and dates)): A0 False, A1 False, A4 CANDIDATE
- dev_alt_p5 (scanned two-field alteration): A0 False, A1 False, A4 NOT_MATCHED
- heldout_alt_p2 (one altered critical field): A0 False, A1 True, A4 CANDIDATE
- heldout_alt_p3 (two altered fields (identity)): A0 False, A1 False, A4 CANDIDATE
- heldout_alt_p4 (three altered fields (number and dates)): A0 False, A1 True, A4 CANDIDATE
- heldout_alt_p5 (scanned two-field alteration): A0 False, A1 False, A4 NOT_MATCHED

## By transformation type (all splits)

| Transform | Pairs | Labels | A0+ | A1+ | A4 confirmed / candidate / not matched / inconclusive |
|---|---|---|---|---|---|
| different_document | 24 | distinct 24 | 0 | 4 | 0 / 4 / 17 / 3 |
| exact_copy | 3 | reuse 3 | 3 | 3 | 3 / 0 / 0 / 0 |
| field_alteration | 3 | altered 3 | 0 | 3 | 0 / 2 / 1 / 0 |
| field_alteration_1 | 2 | altered 2 | 0 | 2 | 0 / 2 / 0 / 0 |
| field_alteration_2 | 2 | altered 2 | 0 | 1 | 0 / 2 / 0 / 0 |
| field_alteration_2_scan | 2 | altered 2 | 0 | 0 | 0 / 0 / 2 / 0 |
| field_alteration_3 | 2 | altered 2 | 0 | 1 | 0 / 2 / 0 / 0 |
| metadata_resave | 3 | reuse 3 | 0 | 3 | 3 / 0 / 0 / 0 |
| photo_sim | 2 | reuse 2 | 0 | 0 | 0 / 0 / 2 / 0 |
| photo_sim_strong | 1 | reuse 1 | 0 | 0 | 0 / 0 / 1 / 0 |
| poor_scan | 4 | reuse 4 | 0 | 0 | 0 / 0 / 0 / 4 |
| raster_crop_brightness | 2 | reuse 2 | 0 | 0 | 0 / 2 / 0 / 0 |
| raster_rotate270 | 1 | reuse 1 | 0 | 1 | 0 / 1 / 0 / 0 |
| raster_rotate90 | 1 | reuse 1 | 0 | 1 | 0 / 1 / 0 / 0 |
| raster_scan | 4 | reuse 4 | 0 | 0 | 0 / 4 / 0 / 0 |
| vector_crop | 1 | reuse 1 | 0 | 0 | 1 / 0 / 0 / 0 |
| vector_rescale | 3 | reuse 3 | 0 | 1 | 3 / 0 / 0 / 0 |
| vector_rescale_rotate | 1 | reuse 1 | 0 | 1 | 1 / 0 / 0 / 0 |

## By document quality (all splits)

| Quality | Pairs | A4 confirmed / candidate / not matched / inconclusive |
|---|---|---|
| clean | 35 | 11 / 11 / 13 / 0 |
| degraded | 18 | 0 / 9 / 9 / 0 |
| poor | 8 | 0 / 0 / 1 / 7 |

OCR engine: none (n/a); OCR pages 0, unreadable pages 22, inconclusive pairs 7.

Split notes: dev: development (thresholds v1–v2 selected here); dev2: development additions for OCR/photo checks (v3); heldout: held-out v1 — inspected during v2 debugging; not pristine; heldout2: held-out v2 — evaluated in D8 after v3 was frozen; now inspected; dev_alt: alteration suite, development (v4 rule developed here); heldout_alt: alteration suite, held-out — evaluated once after v4 was frozen

## Alteration suite (A4 outcome; altered pairs are review candidates, never confirmations)

| Split | Altered pairs | Candidate | Not matched | Inconclusive | Confirmed |
|---|---|---|---|---|---|
| dev | 1 | 1 | 0 | 0 | 0 |
| dev_alt | 4 | 3 | 1 | 0 | 0 |
| heldout | 1 | 0 | 1 | 0 | 0 |
| heldout2 | 1 | 1 | 0 | 0 | 0 |
| heldout_alt | 4 | 3 | 1 | 0 | 0 |

## Campus-photo experiment (separate; synthetic facades; advisory indicator only)

| Split | TP | FP | TN | FN | Inconclusive |
|---|---|---|---|---|---|
| campus_dev | 3 | 0 | 3 | 0 | 0 |
| campus_heldout | 2 | 0 | 3 | 1 | 0 |

Real printed-and-photographed captures: **BLOCKED** — No real printed-and-photographed captures exist: no camera or printer was available. Use `python -m app.cli capture-kit --out DIR` to prepare them.

Evaluated at 2026-10-25T14:33:46+00:00; fixture manifest: 63 documents (in metrics.json).

## Stages that could not run

- OCR (no local OCR engine configured): image-only pages have no text, so text and field comparison is unavailable for raster copies
