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

EVAL_VERSION = "reuse_eval_v3"  # v3: alteration suite, campus experiment, fixture manifest, timestamp, hard-neg candidates
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
    pages = [engine.PageText(p.page_number, p.text, p.status.value, p.method.value, p.ocr_confidence) for p in text.pages]
    readable = [extraction.PageInput(p.page_number, p.text, p.method, p.lines) for p in text.pages if p.status.value == "ok"]
    fields = extraction.extract_fields(readable, {DocumentCategory(doc.category)}) if readable else []
    evidence = [engine.FieldEvidence(f.field_name, f.raw_value, f.normalized_value, f.page_number, f.evidence_quote,
                                     f.status.value, f.evidence_source, f.evidence_box, f.ocr_confidence) for f in fields]
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
    hard_candidates = sum(1 for r in hard if r[arm].get("outcome") == engine.CANDIDATE)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "pairs": len(binary),
            "precision": ratio(tp, tp + fp, "predicted positives"),
            "recall": ratio(tp, tp + fn, "labelled positives"),
            "hard_negative_fp": hard_fp, "hard_negative_fp_rate": ratio(hard_fp, len(hard), "hard negatives"),
            "hard_negative_candidates": hard_candidates,
            "inconclusive": sum(1 for r in rows if r[arm].get("outcome") == engine.INCONCLUSIVE),
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
        w.writerow(["pair", "split", "label", "hard_negative", "scenario", "transform", "quality", "a0", "a1_distance", "a1", "a4_outcome",
                    "text_jaccard", "phash_distance", "geo_status", "geo_inliers", "diff_cells", "field_agree",
                    "field_conflict", "field_inconclusive"])
        for r in self.data["pairs"]:
            w.writerow([r["pair"], r["split"], r["label"], r["hard_negative"], r["scenario"], r.get("transform"), r.get("quality"),
                        r["A0"]["positive"],
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
            m4 = arms["A4"]
        lines += ["", f"A4 outcomes: " + ", ".join(f"{k} {v}" for k, v in o.items())
                  + f". Hard negatives surfaced as CANDIDATE (review, not confirmed): {m4.get('hard_negative_candidates', 0)}.", ""]
        f = d["field_exact_match"]
        t = d["evidence_traceability"]
        lines += ["## Critical-field exact match", "", "| Field | Exact / evaluated |", "|---|---|"]
        lines += [f"| {k} | {v['numerator']}/{v['denominator']} |" for k, v in f.items()]
        lines += ["", f"Evidence traceability (A4): {t['numerator']}/{t['denominator']} source references valid.", "",
                  "## Altered pairs (reported separately)", ""]
        lines += [f"- {r['pair']} ({r['scenario']}): A0 {r['A0']['positive']}, A1 {r['A1']['positive']}, A4 {r['A4']['outcome']}"
                  for r in d["pairs"] if r["label"] == "altered"]
        lines += ["", "## By transformation type (all splits)", "", "| Transform | Pairs | Labels | A0+ | A1+ | A4 confirmed / candidate / not matched / inconclusive |",
                  "|---|---|---|---|---|---|"]
        for k, t in sorted(d.get("by_transform", {}).items()):
            a4 = t["A4"]
            lines.append(f"| {k} | {t['pairs']} | {', '.join(f'{lb} {n}' for lb, n in t['labels'].items())} | {t['A0_pos']} | {t['A1_pos']} | "
                         f"{a4['MATCH_CONFIRMED_FOR_REVIEW']} / {a4['CANDIDATE']} / {a4['NOT_MATCHED']} / {a4['INCONCLUSIVE']} |")
        lines += ["", "## By document quality (all splits)", "", "| Quality | Pairs | A4 confirmed / candidate / not matched / inconclusive |", "|---|---|---|"]
        for k, t in sorted(d.get("by_quality", {}).items()):
            a4 = t["A4"]
            lines.append(f"| {k} | {t['pairs']} | {a4['MATCH_CONFIRMED_FOR_REVIEW']} / {a4['CANDIDATE']} / {a4['NOT_MATCHED']} / {a4['INCONCLUSIVE']} |")
        env = d["environment"]
        lines += ["", f"OCR engine: {env.get('ocr_engine') or 'none'} ({env.get('ocr_engine_version') or 'n/a'}); "
                  f"OCR pages {d['failures'].get('ocr_pages')}, unreadable pages {d['failures'].get('unreadable_pages')}, "
                  f"inconclusive pairs {d['failures']['inconclusive']}.",
                  "", "Split notes: " + "; ".join(f"{k}: {v}" for k, v in env.get("split_notes", {}).items())]
        if d.get("alteration_suite"):
            lines += ["", "## Alteration suite (A4 outcome; altered pairs are review candidates, never confirmations)", "",
                      "| Split | Altered pairs | Candidate | Not matched | Inconclusive | Confirmed |", "|---|---|---|---|---|---|"]
            for split, a in d["alteration_suite"].items():
                lines.append(f"| {split} | {a['pairs']} | {a['candidate']} | {a['not_matched']} | {a['inconclusive']} | {a['confirmed']} |")
        c = d.get("campus_experiment")
        if c:
            lines += ["", "## Campus-photo experiment (separate; synthetic facades; advisory indicator only)", "",
                      "| Split | TP | FP | TN | FN | Inconclusive |", "|---|---|---|---|---|---|"]
            for split, m in c["metrics"].items():
                lines.append(f"| {split} | {m['tp']} | {m['fp']} | {m['tn']} | {m['fn']} | {m['inconclusive']} |")
        pc = d.get("physical_capture") or {}
        lines += ["", f"Real printed-and-photographed captures: **{pc.get('status')}** — {pc.get('reason', '')}",
                  "", f"Evaluated at {d.get('evaluated_at')}; fixture manifest: {len(d.get('fixture_manifest', []))} documents (in metrics.json)."]
        lines += ["", "## Stages that could not run", ""] + [f"- {s}" for s in d["environment"]["unavailable_stages"] or ["none"]]
        return "\n".join(lines) + "\n"


def evaluate(ds: Dataset | None = None, *, ocr: pdf_text.OcrEngine | None = None,
             config: engine.ReuseConfig = engine.DEFAULT_CONFIG,
             splits: tuple[str, ...] = ("dev", "dev2", "dev_alt", "heldout", "heldout2", "heldout_alt"),
             include_campus: bool = True,
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
            "transform": p.transform, "quality": p.quality,
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
                   "rule": (res.fusion or {}).get("rule"),
                   "regions_on_fields": ((res.fusion or {}).get("regions") or {}).get("regions_on_critical_fields"),
                   "text_low_quality": bool(res.text.get("low_quality")),
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
        unavailable.append("OCR (no local OCR engine configured): image-only pages have no text, so text and field "
                           "comparison is unavailable for raster copies")
    for r in rows:
        r["A4"].pop("_result")
    by_transform: dict = {}
    by_quality: dict = {}
    for r in rows:
        for key, table in ((r["transform"], by_transform), (r["quality"], by_quality)):
            t = table.setdefault(key, {"pairs": 0, "labels": {}, "A0_pos": 0, "A1_pos": 0, "A4": {o: 0 for o in engine.OUTCOMES}})
            t["pairs"] += 1
            t["labels"][r["label"]] = t["labels"].get(r["label"], 0) + 1
            t["A0_pos"] += int(r["A0"]["positive"])
            t["A1_pos"] += int(r["A1"]["positive"])
            t["A4"][r["A4"]["outcome"]] += 1
    field_by_label: dict = {}
    for r in rows:
        f = field_by_label.setdefault(r["label"], {"agree": 0, "conflict": 0, "inconclusive": 0})
        for k in f:
            f[k] += r["A4"]["fields"][k]
    ocr_pages = sum(engine.provenance(i)["ocr_pages"] for i in inputs.values())
    unreadable = sum(engine.provenance(i)["unreadable_pages"] for i in inputs.values())
    lat = sorted(r["A4"]["latency_ms"] for r in rows)
    alteration = {}
    for split in splits:
        alt = [r for r in rows if r["split"] == split and r["label"] == "altered"]
        if alt:
            alteration[split] = {"pairs": len(alt), "candidate": sum(r["A4"]["outcome"] == engine.CANDIDATE for r in alt),
                                 "not_matched": sum(r["A4"]["outcome"] == engine.NOT_MATCHED for r in alt),
                                 "inconclusive": sum(r["A4"]["outcome"] == engine.INCONCLUSIVE for r in alt),
                                 "confirmed": sum(r["A4"]["outcome"] == engine.MATCH_CONFIRMED for r in alt),
                                 "by_pair": {r["pair"]: r["A4"]["outcome"] for r in alt}}
    manifest = [{"key": k, "case": d.case, "category": d.category, "recipe": d.recipe, "source": d.source_key,
                 "text_layer": d.has_text_layer, "sha256": _sha(d.pdf)} for k, d in sorted(ds.docs.items())]
    from datetime import datetime, timezone
    from pathlib import Path as _P

    from app.services import physical_capture
    campus = None
    if include_campus:
        from app.services.image_reuse import evaluate_campus
        campus = evaluate_campus()
    capture = physical_capture.status(_P(__file__).resolve().parents[3] / "docs" / "evaluation" / "physical-capture" / "manifest.json")
    data = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_version": EVAL_VERSION, "dataset_version": ds.version, "dataset_digest": dataset_digest(ds),
        "config_version": config.version, "pipeline_version": engine.pipeline_version(config),
        "config": config.snapshot(), "a1_threshold": a1_threshold, "splits": list(splits),
        "composition": ds.composition(), "metrics": metrics, "a4_outcomes": outcomes,
        "field_exact_match": fem, "evidence_traceability": ratio(t_num, t_den, "surfaced source references"),
        "failures": {"inconclusive": sum(1 for r in rows if r["A4"]["outcome"] == engine.INCONCLUSIVE),
                     "text_unavailable_pairs": sum(1 for r in rows if r["A4"]["text_status"] != "computed"),
                     "low_quality_text_pairs": sum(1 for r in rows if r["A4"]["text_low_quality"]),
                     "ocr_pages": ocr_pages, "unreadable_pages": unreadable, "documents": len(inputs)},
        "by_transform": by_transform, "by_quality": by_quality, "field_outcomes_by_label": field_by_label,
        "alteration_suite": alteration, "campus_experiment": campus, "physical_capture": capture,
        "fixture_manifest": manifest,
        "latency": {"a4_per_pair_ms_median": lat[len(lat) // 2] if lat else None, "a4_per_pair_ms_max": lat[-1] if lat else None,
                    "document_preparation_ms_total": round(sum(prep_ms.values()), 1),
                    "note": "A4 per-pair latency includes text extraction/OCR of both documents (not cached in evaluation)."},
        "environment": {"ocr_available": bool(ocr and ocr.available), "opencv_version": CV2_VERSION,
                        "ocr_engine": getattr(ocr, "name", None) if ocr and ocr.available else None,
                        "ocr_engine_version": ocr.engine_version() if ocr and ocr.available and hasattr(ocr, "engine_version") else None,
                        "unavailable_stages": unavailable,
                        "split_notes": {"dev": "development (thresholds v1–v2 selected here)",
                                        "dev2": "development additions for OCR/photo checks (v3)",
                                        "heldout": "held-out v1 — inspected during v2 debugging; not pristine",
                                        "heldout2": "held-out v2 — evaluated in D8 after v3 was frozen; now inspected",
                                        "dev_alt": "alteration suite, development (v4 rule developed here)",
                                        "heldout_alt": "alteration suite, held-out — evaluated once after v4 was frozen"}},
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
