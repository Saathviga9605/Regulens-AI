# Cross-case reuse evaluation (reuse_eval_v1)

Dataset `reuse_ds_v1` (digest `c579ee4e0209f12c`), config `reuse_thr_v1`, pipeline `reuse_cascade_v1+txtnorm_v1+phash_dct_v1+orb_ransac_v1+fieldcmp_v1`. A1 threshold: pHash distance ≤ 0 (dev-selected).
OCR available: False; OpenCV: 5.0.0.

Synthetic data only; tiny sample — no statistical significance is claimed.

## dev

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 6 | 4 | 1.00 (1/1) | 0.20 (1/5) | 0/5 | 0.0 |
| A1 | 3 | 0 | 6 | 2 | 1.00 (3/3) | 0.60 (3/5) | 0/5 | 176.9 |
| A4 | 3 | 0 | 6 | 2 | 1.00 (3/3) | 0.60 (3/5) | 0/5 | 8797.6 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 3, CANDIDATE 3, NOT_MATCHED 5, INCONCLUSIVE 1

## heldout

| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |
|---|---|---|---|---|---|---|---|---|
| A0 | 1 | 0 | 8 | 6 | 1.00 (1/1) | 0.14 (1/7) | 0/7 | 0.0 |
| A1 | 3 | 2 | 6 | 4 | 0.60 (3/5) | 0.43 (3/7) | 2/7 | 165.4 |
| A4 | 4 | 0 | 8 | 3 | 1.00 (4/4) | 0.57 (4/7) | 0/7 | 9290.6 |

A4 outcomes: MATCH_CONFIRMED_FOR_REVIEW 4, CANDIDATE 4, NOT_MATCHED 7, INCONCLUSIVE 1

## Critical-field exact match

| Field | Exact / evaluated |
|---|---|
| institution_name | 18/23 |
| certificate_number | 18/23 |
| issue_date | 18/23 |

Evidence traceability (A4): 90/90 source references valid.

## Altered pairs (reported separately)

- dev_p10 (critical-field alteration): A0 False, A1 True, A4 CANDIDATE
- ho_p13 (critical-field alteration (dates)): A0 False, A1 True, A4 NOT_MATCHED

## Stages that could not run

- OCR (Tesseract not configured): image-only pages have no text, so text and field comparison is unavailable for raster copies
