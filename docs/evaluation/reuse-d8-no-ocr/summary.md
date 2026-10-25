# Cross-case reuse evaluation (reuse_eval_v2)

Dataset `reuse_ds_v2` (digest `d0db4929ba6de6e4`), config `reuse_thr_v3`, pipeline `reuse_cascade_v3+txtnorm_v2+phash_dct_v2+orb_ransac_v1+fieldcmp_v2+fusion_v1`. A1 threshold: pHash distance ≤ 0 (dev-selected).
OCR available: False; OpenCV: 5.0.0.

Synthetic data only; tiny sample — no statistical significance is claimed.

## dev

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 6 | 4 | 1.00 (1/1) | 0.20 (1/5) | 0/5 | 0.0 |
| A1 | 3 | 0 | 6 | 2 | 1.00 (3/3) | 0.60 (3/5) | 0/5 | 197.3 |
| A4 | 3 | 0 | 6 | 2 | 1.00 (3/3) | 0.60 (3/5) | 0/5 | 8093.4 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 3, CANDIDATE 3, NOT_MATCHED 5, INCONCLUSIVE 1

## dev2

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 0 | 0 | 2 | 4 | n/a (0/0) | 0.00 (0/4) | 0/2 | 0.0 |
| A1 | 0 | 0 | 2 | 4 | n/a (0/0) | 0.00 (0/4) | 0/2 | 78.7 |
| A4 | 0 | 0 | 2 | 4 | n/a (0/0) | 0.00 (0/4) | 0/2 | 9014.5 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 0, CANDIDATE 1, NOT_MATCHED 4, INCONCLUSIVE 1

## heldout

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 8 | 6 | 1.00 (1/1) | 0.14 (1/7) | 0/7 | 0.0 |
| A1 | 3 | 2 | 6 | 4 | 0.60 (3/5) | 0.43 (3/7) | 2/7 | 189.0 |
| A4 | 4 | 0 | 8 | 3 | 1.00 (4/4) | 0.57 (4/7) | 0/7 | 8941.3 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 4, CANDIDATE 4, NOT_MATCHED 7, INCONCLUSIVE 1

## heldout2

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 6 | 5 | 1.00 (1/1) | 0.17 (1/6) | 0/5 | 0.0 |
| A1 | 3 | 1 | 5 | 3 | 0.75 (3/4) | 0.50 (3/6) | 1/5 | 158.6 |
| A4 | 2 | 0 | 6 | 4 | 1.00 (2/2) | 0.33 (2/6) | 0/5 | 9185.0 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 2, CANDIDATE 3, NOT_MATCHED 6, INCONCLUSIVE 2

## Critical-field exact match

| Field | Exact / evaluated |
|---|---|
| institution_name | 26/40 |
| certificate_number | 26/40 |
| issue_date | 26/40 |

Evidence traceability (A4): 120/120 source references valid.

## Altered pairs (reported separately)

- dev_p10 (critical-field alteration): A0 False, A1 True, A4 CANDIDATE
- ho_p13 (critical-field alteration (dates)): A0 False, A1 True, A4 NOT_MATCHED
- h2_p11 (certificate number changed): A0 False, A1 True, A4 CANDIDATE

## By transformation type (all splits)

| Transform | Pairs | Labels | A0+ | A1+ | A4 confirmed / candidate / not matched / inconclusive |
|---|---|---|---|---|---|
| different_document | 22 | distinct 22 | 0 | 3 | 0 / 1 / 18 / 3 |
| exact_copy | 3 | reuse 3 | 3 | 3 | 3 / 0 / 0 / 0 |
| field_alteration | 3 | altered 3 | 0 | 3 | 0 / 2 / 1 / 0 |
| metadata_resave | 3 | reuse 3 | 0 | 3 | 3 / 0 / 0 / 0 |
| photo_sim | 2 | reuse 2 | 0 | 0 | 0 / 0 / 2 / 0 |
| photo_sim_strong | 1 | reuse 1 | 0 | 0 | 0 / 0 / 1 / 0 |
| poor_scan | 2 | reuse 2 | 0 | 0 | 0 / 0 / 0 / 2 |
| raster_crop_brightness | 2 | reuse 2 | 0 | 0 | 0 / 2 / 0 / 0 |
| raster_rotate270 | 1 | reuse 1 | 0 | 1 | 0 / 1 / 0 / 0 |
| raster_rotate90 | 1 | reuse 1 | 0 | 1 | 0 / 1 / 0 / 0 |
| raster_scan | 4 | reuse 4 | 0 | 0 | 0 / 4 / 0 / 0 |
| vector_crop | 1 | reuse 1 | 0 | 0 | 1 / 0 / 0 / 0 |
| vector_rescale | 1 | reuse 1 | 0 | 0 | 1 / 0 / 0 / 0 |
| vector_rescale_rotate | 1 | reuse 1 | 0 | 1 | 1 / 0 / 0 / 0 |

## By document quality (all splits)

| Quality | Pairs | A4 confirmed / candidate / not matched / inconclusive |
|---|---|---|
| clean | 25 | 9 / 2 / 14 / 0 |
| degraded | 16 | 0 / 9 / 7 / 0 |
| poor | 6 | 0 / 0 / 1 / 5 |

OCR engine: none (n/a); OCR pages 0, unreadable pages 18, inconclusive pairs 5.

Split notes: dev: development (thresholds v1–v2 selected here); dev2: development additions for OCR/photo checks (v3); heldout: held-out v1 — inspected during v2 debugging; not pristine; heldout2: fresh held-out — evaluated once after v3 was frozen

## Stages that could not run

- OCR (no local OCR engine configured): image-only pages have no text, so text and field comparison is unavailable for raster copies
