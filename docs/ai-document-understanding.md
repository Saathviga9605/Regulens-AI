# Evidence-grounded document understanding and reuse detection (Deliverable 8)

> **Deliverable 9:** cascade v4 (localized-alteration rule, address compared), dataset `reuse_ds_v3` and current results are in [d9-acceptance.md](d9-acceptance.md). The D8 results below remain the historical record.

ReguLens runs entirely on the local machine. No paid API, API key, cloud inference or network call is used for
analysis, and no model weights are downloaded at start-up. This page states exactly which component is which.

## What each component is

| Capability | Component | Kind |
|---|---|---|
| Text from text-layer PDFs | PyMuPDF text extraction | deterministic |
| Text from scanned / photographed pages | **RapidOCR** (PP-OCR detection + recognition neural networks, ONNX Runtime, CPU) or **Tesseract** if installed | OCR (neural / classical) |
| Field extraction (institution, certificate no., issuer, dates, survey/property ids, address, references, area) | labelled-field rules `label_regex_v2` with evidence quote, page, coordinates | deterministic rules (not an LLM) |
| Page retrieval | DCT perceptual hash `phash_dct_v2` with rotation variants and photo rectification | classical computer vision |
| Alignment and difference regions | OpenCV ORB + RANSAC homography, ECC refinement, intensity residual | classical computer vision |
| Evidence fusion and outcome | `fusion_v1` rules (transparent; nothing trained on the small labelled set) | deterministic rules |
| Reviewer explanation | `explain_v1`, generated from the stored evidence record | deterministic templates |
| Local vision / language model | **none configured** — reported as such by `/system/info` | — |

No local LLM or vision model was found or installed on the verification machine (no GPU, no Ollama or similar
runtime), so none is integrated. Explanations are therefore generated deterministically; nothing is presented as
model output.

## OCR

* Provider selection: `REGULENS_OCR_ENGINE=auto|tesseract|rapidocr|none` (default `auto`: Tesseract if its
  executable is found, else RapidOCR if installed, else none). Explicitly requested but missing engines are reported
  unavailable, never silently replaced, and never by a remote service. `/system/info` → `ai_capabilities`.
* Text-layer pages are never OCR'd. Pages with too little text are rendered at `REGULENS_OCR_DPI` (default 200,
  capped at 20 MP) and recognised; only if the upright reading is weak (too little text or mean score < 0.60) are
  90/180/270° tried, and a rotation is kept only if it scores 1.5× better. No other preprocessing is applied, so
  stamps, signatures and identifiers are not altered.
* Each page stores the OCR engine, mean engine score, rotation and its **lines** with boxes. Each extracted field
  stores `evidence_source` (text_layer / ocr), `evidence_box` and `ocr_confidence` (lowest score of the cited
  line), separately from extraction confidence. Fields from lines scoring < 0.80 get confidence *low* and a warning.
* **Coordinate convention:** `[x0, y0, x1, y1]` normalised to 0–1 of the displayed page, origin top-left (after
  any OCR rotation, which is recorded). Text-layer lines carry `confidence = null`.
* OCR scores are the engine's own recognition scores, **not calibrated probabilities of correctness**.
* Caching: processing results are keyed by document SHA-256 + pipeline version (which includes the extractor
  version), so OCR is not repeated for unchanged documents; reuse descriptors are keyed by feature version.
* Measured: RapidOCR takes ≈ 5–7 s per A4 page at 200 dpi on a 16-core CPU; it drops spaces between words
  ("DateofIssue:27August2025"), which `label_regex_v2` (whitespace-tolerant labels, digit/letter split for dates)
  and `fieldcmp_v2` (whitespace-insensitive names) handle. Identifiers were read exactly in the fixtures.
* OCR text is untrusted data: it is only matched against labels and compared; it is never executed or followed.

**Installation status on the verification machine:** Tesseract **not installed** (installing it needs an
administrator installer; not done). RapidOCR **installed in the project venv** (`requirements-ocr.txt`, see README).

## Cascade v3 changes (`reuse_cascade_v3`, thresholds `reuse_thr_v3`)

* **L1** `txtnorm_v2`: shingles ignore whitespace (reflow, line wrapping, OCR spacing). Provenance per side
  (text-layer pages, OCR pages, mean OCR score, unreadable pages). Text whose OCR mean score is < 0.60 is reported
  but never used as strong or "unrelated" evidence.
* **L2** `phash_dct_v2`: photographed sheets (a bright quadrilateral covering 30–97 % of the frame) are rectified
  before hashing. Dev2 photos: distance 20 → 4/8.
* **Fields** `fieldcmp_v2`: names compare ignoring whitespace; a disagreement involving an OCR line scoring < 0.80 is
  *inconclusive* (possible misread), not a conflict.
* **Region-aware comparison:** L3 difference regions are mapped onto side-A field evidence boxes
  (`visual_difference` per field; regions on critical fields vs elsewhere).
* **L4 fusion** `fusion_v1`: supporting / contradicting / unavailable / neutral signals, each with the evidence path,
  the rule that decided the outcome, field and region summaries, text quality. Stored in `match_evidence.fusion`.
* **Explanations** `explain_v1`: statements generated only from stored values; each lists the evidence paths and
  values it uses. A test checks every number and quote in every statement against the evidence record.
* Decision rules are the v2 rules plus the OCR-quality guard; the two OCR thresholds (0.60 / 0.80) were set a priori
  and did not change any dev outcome. No threshold was tuned on held-out data.

## Dataset `reuse_ds_v2` and splits

v1's 28 documents are byte-identical (subset digest `c579ee4e0209f12c`). Added: `dev2` (simulated photographs —
perspective, lighting gradient, noise, blur, JPEG — poor scans, raster scan, photographed same-template
negatives) and `heldout2` (new fictional issuer, institutions and documents: exact, metadata, photo, scan, 270°
rotation, poor scan, same-template / same-issuer / seal-only / same-institution negatives, an alteration). Photos are
**simulated**; no real phone photographs were taken. Campus-photo pairs are not included.

| Split | Role | Pairs (reuse / altered / distinct, hard neg.) |
|---|---|---|
| dev | thresholds v1–v2 selected here | 12 (5 / 1 / 6, 5) |
| dev2 | OCR/photo development checks for v3 | 6 (4 / 0 / 2, 2) |
| heldout | v1 held-out — **inspected during v2 debugging, not pristine** | 16 (7 / 1 / 8, 7) |
| heldout2 | fresh — evaluated once after v3 was frozen | 13 (6 / 1 / 6, 5) |

## Measured results (`docs/evaluation/reuse-d8/`, OCR = RapidOCR; `reuse-d8-no-ocr/` without OCR)

Same labelled pairs for every arm; A4 positive = `MATCH_CONFIRMED_FOR_REVIEW`; altered pairs excluded from binary
counts. Synthetic prototype benchmark — far too small for statistical claims.

| Split | A0 recall | A1 precision / recall (hard-neg FP) | A4 with OCR: TP FP TN FN | A4 recall with / without OCR | A4 hard-neg FP |
|---|---|---|---|---|---|
| dev | 1/5 | 3/3, 3/5 (0/5) | 5 0 6 0 | 5/5 / 3/5 | 0/5 |
| dev2 | 0/4 | n/a (0/0), 0/4 (0/2) | 3 0 2 1 | 3/4 / 0/4 | 0/2 |
| heldout (inspected) | 1/7 | 3/5, 3/7 (2/7) | 7 0 8 0 | 7/7 / 4/7 | 0/7 |
| **heldout2 (fresh)** | 1/6 | 3/4, 3/6 (1/5) | 5 0 6 1 | **5/6 / 2/6** | 0/5 |

* By transformation (all splits, with OCR): raster scans 4/4, simulated photos 3/3, rotations 2/2, metadata/exact/
  vector copies all confirmed; poor scans 0/2 confirmed (both `INCONCLUSIVE` — intended); 22 different-document pairs:
  19 not matched, 3 inconclusive, 0 confirmed; alterations: 2 candidate, 1 not matched (`ho_p13`, two dates changed).
* By quality: clean 25 pairs (9 confirmed / 2 candidate / 14 not matched), degraded 16 (10 / 0 / 6 / 0), poor 6
  (1 confirmed — the strong simulated photo, a true positive — 5 inconclusive).
* Critical-field exact match with OCR: institution 32/40, certificate number 38/40, issue date 35/40 (without OCR
  26/40 each). Evidence traceability 196/196. Inconclusive pairs 5; unreadable pages 6.
* Without OCR, photos fall to `NOT_MATCHED` (lighting leaves >4 difference regions) and raster copies stay
  `CANDIDATE` — conservative misses, no false positives.
* Latency: A4 ≈ 0.4–0.8 s per pair of comparison work plus ≈ 5–7 s per OCR page (OCR runs once per document and is
  cached in the application).

## Known limitations

* Field extraction is rule-based; unusual layouts or wording are missed. OCR quality drives institution/date
  accuracy (32/40, 35/40).
* Poor scans are reported inconclusive rather than confirmed; real phone photos may behave differently from the
  simulation.
* The residual difference map is sensitive to photographic lighting; photo pairs rely on OCR text and fields.
* Alterations of two or more fields are indistinguishable by rule from a different certificate on the same template.
* No local LLM or vision model is integrated.
