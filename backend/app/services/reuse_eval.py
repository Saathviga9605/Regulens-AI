"""A0 / A1 / A4 evaluation of cross-case reuse detection on the synthetic ``reuse_ds_v1`` dataset.

* **A0 — exact hash:** predicted positive iff SHA-256 equal.
* **A1 — perceptual hash only:** predicted positive iff the best page pHash distance (with rotation variants) is at
  or below ``A1_PHASH_THRESHOLD``, chosen on the dev split only (``select_a1_threshold``) and frozen here.
* **A4 — full cascade:** predicted positive iff the outcome is ``MATCH_CONFIRMED_FOR_REVIEW``.

All three arms use exactly the same labelled pairs. Binary counts use ``reuse`` (positive) and ``distinct``
(negative) pairs; ``altered`` pairs are reported separately with their outcomes. ``INCONCLUSIVE`` and
``CANDIDATE`` are *not* predicted positives for A4 and are counted separately. Undefined ratios (zero
denominators) are reported as ``null`` with the reason — never as 0 or 1. With a dataset this small no
statistical significance is claimed.

Text is extracted with the production text pipeline (PyMuPDF text layer; OCR only if Tesseract is configured) and
fields with the production extractor, so evaluation exercises the same code as the application.
"""

from __future__ import annotations

import csv
import io
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.models.enums import DocumentCategory
from app.services import extraction, pdf_text
from app.services import reuse_engine as engine
from app.services.reuse_dataset import Dataset, FixtureDoc, build_dataset, dataset_digest

EVAL_VERSION = "reuse_eval_v1"
# Frozen after dev-split selection (see docs/reuse-detection.md, "Threshold selection").
A1_PHASH_THRESHOLD = 0


def _sha(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def fixture_input(doc: FixtureDoc, ocr: pdf_text.OcrEngine | None, *, min_chars: int = 20, dpi: int = 300) -> engine.DocumentInput:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "doc.pdf"
        path.write_bytes(doc.pdf)
        text = pdf_text.extract_text(path, ocr, min_chars=min_chars, max_pages=10, dpi=dpi)
    pages = [engine.PageText(p.page_number, p.text, p.status.value) for p in text.pages]
    readable = [extraction.PageInput(p.page_number, p.text, p.method) for p in text.pages if p.status.value == "ok"]
    fields = extraction.extract_fields(readable, {DocumentCategory(doc.category)}) if readable else []
    evidence = [engine.FieldEvidence(f.field_name, f.raw_value, f.normalized_value, f.page_number, f.evidence_quote,
                                     f.status.value) for f in fields]
    status = "available" if text.status.value != "failed" else "failed"
    return engine.DocumentInput(doc.key, doc.case, _sha(doc.pdf), doc.pdf, pages, evidence, text_status=status)


def ratio(num: int, den: int, what: str) -> dict:
    if den == 0:
        return {"value": None, "numerator": num, "denominator": den, "note": f"undefined: no {what}"}
    return {"value": round(num / den, 4), "numerator": num, "denominator": den}


def confusion(rows: list[dict], arm: str) -> dict:
    binary = [r for r in rows if r["label"] in ("reuse", "distinct")]
    tp = sum(1 for r in binary if r["label"] == "reuse" and r[arm]["positive"])
    fn = sum(1 for r in binary if r["label"] == "reuse" and not r[arm]["positive"])
    fp = sum(1 for r in binary if r["label"] == "distinct" and r[arm]["positive"])
    tn = sum(1 for r in binary if r["label"] == "distinct" and not r[arm]["positive"])
    hard = [r for r in binary if r["hard_negative"]]
    hard_fp = sum(1 for r in hard if r[arm]["positive"])
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "pairs": len(binary),
            "precision": ratio(tp, tp + fp, "predicted positives"),
            "recall": ratio(tp, tp + fn, "labelled positives"),
            "hard_negative_fp": hard_fp, "hard_negative_fp_rate": ratio(hard_fp, len(hard), "hard negatives"),
            "latency_ms_total": round(sum(r[arm]["latency_ms"] for r in rows), 1),
            "latency_ms_mean": round(sum(r[arm]["latency_ms"] for r in rows) / len(rows), 2) if rows else None}


@dataclass
class EvalResult:
    data: dict

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["split", "arm", "tp", "fp", "tn", "fn", "precision", "precision_num", "precision_den", "recall",
                    "recall_num", "recall_den", "hard_negative_fp", "hard_negatives", "latency_ms_total"])
        for split, arms in self.data["metrics"].items():
            for arm, m in arms.items():
                w.writerow([split, arm, m["tp"], m["fp"], m["tn"], m["fn"], m["precision"]["value"],
                            m["precision"]["numerator"], m["precision"]["denominator"], m["recall"]["value"],
                            m["recall"]["numerator"], m["recall"]["denominator"], m["hard_negative_fp"],
                            m["hard_negative_fp_rate"]["denominator"], m["latency_ms_total"]])
        w.writerow([])
        w.writerow(["pair", "split", "label", "hard_negative", "scenario", "a0", "a1_distance", "a1", "a4_outcome",
                    "text_jaccard", "phash_distance", "geo_status", "geo_inliers", "diff_cells", "field_agree",
                    "field_conflict", "field_inconclusive"])
        for r in self.data["pairs"]:
            w.writerow([r["pair"], r["split"], r["label"], r["hard_negative"], r["scenario"], r["A0"]["positive"],
                        r["A1"]["distance"], r["A1"]["positive"], r["A4"]["outcome"], r["A4"]["text_jaccard"],
                        r["A4"]["phash_distance"], r["A4"]["geo_status"], r["A4"]["geo_inliers"], r["A4"]["diff_cells"],
                        r["A4"]["fields"]["agree"], r["A4"]["fields"]["conflict"], r["A4"]["fields"]["inconclusive"]])
        return buf.getvalue()

    def to_markdown(self) -> str:
        d = self.data
        lines = [f"# Cross-case reuse evaluation ({d['eval_version']})", "",
                 f"Dataset `{d['dataset_version']}` (digest `{d['dataset_digest']}`), config `{d['config_version']}`, "
                 f"pipeline `{d['pipeline_version']}`. A1 threshold: pHash distance ≤ {d['a1_threshold']} (dev-selected).",
                 f"OCR available: {d['environment']['ocr_available']}; OpenCV: {d['environment']['opencv_version'] or 'not installed'}.",
                 "", "Synthetic data only; tiny sample — no statistical significance is claimed.", ""]
        for split, arms in d["metrics"].items():
            lines += [f"## {split}", "", "| Arm | TP | FP | TN | FN | Precision | Recall | Hard-neg FP | Latency (ms) |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for arm, m in arms.items():
                p, r, h = m["precision"], m["recall"], m["hard_negative_fp_rate"]
                fmt = lambda x: "n/a" if x["value"] is None else f"{x['value']:.2f}"  # noqa: E731
                lines.append(f"| {arm} | {m['tp']} | {m['fp']} | {m['tn']} | {m['fn']} | {fmt(p)} ({p['numerator']}/{p['denominator']}) "
                             f"| {fmt(r)} ({r['numerator']}/{r['denominator']}) | {m['hard_negative_fp']}/{h['denominator']} "
                             f"| {m['latency_ms_total']} |")
            o = d["a4_outcomes"][split]
            lines += ["", f"A4 outcomes: " + ", ".join(f"{k} {v}" for k, v in o.items()), ""]
        f = d["field_exact_match"]
        t = d["evidence_traceability"]
        lines += ["## Critical-field exact match", "", "| Field | Exact / evaluated |", "|---|---|"]
        lines += [f"| {k} | {v['numerator']}/{v['denominator']} |" for k, v in f.items()]
        lines += ["", f"Evidence traceability (A4): {t['numerator']}/{t['denominator']} source references valid.", "",
                  "## Altered pairs (reported separately)", ""]
        lines += [f"- {r['pair']} ({r['scenario']}): A0 {r['A0']['positive']}, A1 {r['A1']['positive']}, A4 {r['A4']['outcome']}"
                  for r in d["pairs"] if r["label"] == "altered"]
        lines += ["", "## Stages that could not run", ""] + [f"- {s}" for s in d["environment"]["unavailable_stages"] or ["none"]]
        return "\n".join(lines) + "\n"


def evaluate(ds: Dataset | None = None, *, ocr: pdf_text.OcrEngine | None = None,
             config: engine.ReuseConfig = engine.DEFAULT_CONFIG, splits: tuple[str, ...] = ("dev", "heldout"),
             a1_threshold: int = A1_PHASH_THRESHOLD) -> EvalResult:
    from app.services.reuse_visual import CV2_VERSION

    ds = ds or build_dataset()
    inputs: dict[str, engine.DocumentInput] = {}
    prep_ms: dict[str, float] = {}
    for key in {k for p in ds.pairs if p.split in splits for k in (p.a, p.b)}:
        t0 = time.perf_counter()
        inputs[key] = fixture_input(ds.docs[key], ocr)
        prep_ms[key] = (time.perf_counter() - t0) * 1000

    rows = []
    for p in ds.pairs:
        if p.split not in splits:
            continue
        a, b = inputs[p.a], inputs[p.b]
        t0 = time.perf_counter()
        a0 = a.sha256 == b.sha256
        a0_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        vis = engine.visual_stage(a, b, config)
        a1_dist = vis.get("distance")
        a1 = a1_dist is not None and a1_dist <= a1_threshold
        a1_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        res = engine.compare(a, b, config)
        a4_ms = (time.perf_counter() - t0) * 1000 + prep_ms[p.a] + prep_ms[p.b]
        geo = res.geometric or {}
        rows.append({
            "pair": p.key, "split": p.split, "label": p.label, "hard_negative": p.hard_negative, "scenario": p.scenario,
            "hero": p.hero, "a": p.a, "b": p.b, "recipe_a": ds.docs[p.a].recipe, "recipe_b": ds.docs[p.b].recipe,
            "A0": {"positive": a0, "latency_ms": round(a0_ms, 3)},
            "A1": {"positive": a1, "distance": a1_dist, "latency_ms": round(a1_ms, 2)},
            "A4": {"positive": res.outcome == engine.MATCH_CONFIRMED, "outcome": res.outcome,
                   "latency_ms": round(a4_ms, 1), "text_jaccard": res.text.get("jaccard"),
                   "text_status": res.text.get("status"), "phash_distance": vis.get("distance"),
                   "geo_status": geo.get("status"), "geo_inliers": geo.get("inliers"),
                   "geo_coverage": geo.get("coverage"),
                   "diff_cells": (geo.get("differences") or {}).get("cells_different"),
                   "fields": {k: res.fields[k] for k in ("agree", "conflict", "inconclusive")},
                   "reasons": res.reasons, "uncertainties": res.uncertainties,
                   "_result": res},
        })

    metrics = {}
    outcomes = {}
    for split in splits:
        srows = [r for r in rows if r["split"] == split]
        metrics[split] = {arm: confusion(srows, arm) for arm in ("A0", "A1", "A4")}
        outcomes[split] = {o: sum(1 for r in srows if r["A4"]["outcome"] == o) for o in engine.OUTCOMES}

    # Critical-field exact match against the generator's expected values.
    fem = {}
    for name in ("institution_name", "certificate_number", "issue_date"):
        num = den = 0
        for key, inp in inputs.items():
            expected = ds.docs[key].expected_fields.get(name)
            if not expected:
                continue
            den += 1
            got = next((f for f in inp.fields if f.field_name == name and f.status == "extracted"), None)
            if got is None:
                continue
            value = (got.normalized_value or {}).get("date") if name == "issue_date" else got.raw_value
            num += int(value == expected)
        fem[name] = ratio(num, den, f"documents with an expected {name}")

    # Evidence traceability: each surfaced A4 field comparison / matched page must point at a valid source.
    t_num = t_den = 0
    for r in rows:
        res = r["A4"]["_result"]
        if res.outcome not in (engine.MATCH_CONFIRMED, engine.CANDIDATE):
            continue
        a, b = inputs[r["a"]], inputs[r["b"]]
        for c in res.fields["comparisons"]:
            if c["outcome"] not in ("agree", "conflict"):
                continue
            for side, doc in (("a", a), ("b", b)):
                t_den += 1
                v = c[side]
                page = next((pg for pg in doc.pages if pg.page_number == v["page_number"]), None)
                t_num += int(page is not None and engine.is_grounded(v["evidence_quote"], page.text))
        for mp in res.matched_pages:
            t_den += 2
            t_num += int(1 <= mp["page_a"] <= len(a.descriptors(config))) + int(1 <= mp["page_b"] <= len(b.descriptors(config)))

    unavailable = []
    if CV2_VERSION is None:
        unavailable.append("L3 geometric verification (OpenCV not installed)")
    if not (ocr and ocr.available):
        unavailable.append("OCR (Tesseract not configured): image-only pages have no text, so text and field "
                           "comparison is unavailable for raster copies")
    for r in rows:
        r["A4"].pop("_result")
    data = {
        "eval_version": EVAL_VERSION, "dataset_version": ds.version, "dataset_digest": dataset_digest(ds),
        "config_version": config.version, "pipeline_version": engine.pipeline_version(config),
        "config": config.snapshot(), "a1_threshold": a1_threshold, "splits": list(splits),
        "composition": ds.composition(), "metrics": metrics, "a4_outcomes": outcomes,
        "field_exact_match": fem, "evidence_traceability": ratio(t_num, t_den, "surfaced source references"),
        "failures": {"inconclusive": sum(1 for r in rows if r["A4"]["outcome"] == engine.INCONCLUSIVE),
                     "text_unavailable_pairs": sum(1 for r in rows if r["A4"]["text_status"] != "computed")},
        "environment": {"ocr_available": bool(ocr and ocr.available), "opencv_version": CV2_VERSION,
                        "unavailable_stages": unavailable},
        "pairs": rows,
    }
    return EvalResult(data)


def select_a1_threshold(ds: Dataset | None = None, config: engine.ReuseConfig = engine.DEFAULT_CONFIG) -> dict:
    """Dev split only: the pHash threshold maximising F1 (ties → smallest threshold)."""
    ds = ds or build_dataset()
    inputs = {k: fixture_input(ds.docs[k], None) for p in ds.pairs if p.split == "dev" for k in (p.a, p.b)}
    rows = []
    for p in ds.pairs:
        if p.split != "dev" or p.label == "altered":
            continue
        v = engine.visual_stage(inputs[p.a], inputs[p.b], config)
        rows.append((p.label == "reuse", v.get("distance")))
    best = None
    table = []
    for t in range(0, 33):
        tp = sum(1 for pos, d in rows if pos and d is not None and d <= t)
        fp = sum(1 for pos, d in rows if not pos and d is not None and d <= t)
        fn = sum(1 for pos, d in rows if pos and (d is None or d > t))
        f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        table.append({"threshold": t, "tp": tp, "fp": fp, "fn": fn, "f1": round(f1, 4)})
        if best is None or f1 > best["f1"]:
            best = table[-1]
    return {"selected": best, "table": table, "distances": rows}
