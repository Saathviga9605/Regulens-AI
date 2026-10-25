"""Cross-case document reuse cascade (pure; no database access).

Stages, each reporting its raw metric, method and version:

* **L0 exact** — SHA-256 equality. Establishes byte identity only.
* **L1 text** — ``txtnorm_v2`` normalisation (NFKC, zero-width/soft-hyphen removal, casefold; no punctuation,
  digits or identifiers removed) and character 5-gram shingles computed with whitespace removed, so reflow, line
  wrapping and OCR spacing errors do not change the shingles. Raw metrics: Jaccard similarity and containment.
  Text provenance (text layer vs OCR, OCR engine confidence) is recorded; text read by OCR with low mean
  confidence is reported but never used as strong evidence. Texts below ``min_text_chars`` are *unavailable*.
* **L2 visual** — page pHash with rotation variants (see ``reuse_visual``); best Hamming distance.
* **L3 geometric** — ORB + RANSAC homography on the best-matching page pair, with a residual difference map.
* **Fields** — critical fields compared only when both sides were extracted with a quote grounded in the page
  text (a valid source pointer). Missing, ambiguous or unverified values are *inconclusive*, never a conflict, and
  a disagreement involving a low-confidence OCR value is inconclusive (possible misread).
* **Regions** — difference regions from L3 are mapped onto each field's evidence box (side A), so a changed
  certificate number is distinguished from differences elsewhere on the page.
* **L4 fusion** — ``fusion_v1`` records which signals support, contradict or are unavailable, the rule applied and
  a deterministic, evidence-referenced explanation (``explain``). It is rule-based and transparent; nothing is
  trained on the small labelled set.

The decision (``decide``) is conservative: ``MATCH_CONFIRMED_FOR_REVIEW`` needs byte identity, or strong content
similarity *with* corroboration (agreeing grounded fields, or a verified geometry whose residual map shows no
localized differences) and no conflicting critical field. A shared template, logo, border or a single pHash
threshold is never enough. Outcomes are matching outcomes for human review — not compliance, authenticity or
misconduct findings.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field

from app.services import reuse_visual as visual
from app.services.normalize import collapse_ws, is_grounded, normalize_identifier, normalize_name

ENGINE_VERSION = "reuse_cascade_v3"
TEXT_NORM_VERSION = "txtnorm_v2"
TEXT_METRIC = "char5_shingle_jaccard+containment"
FIELD_COMPARE_VERSION = "fieldcmp_v2"
FUSION_VERSION = "fusion_v1"
EXPLANATION_VERSION = "explain_v1"

MATCH_CONFIRMED = "MATCH_CONFIRMED_FOR_REVIEW"
CANDIDATE = "CANDIDATE"
NOT_MATCHED = "NOT_MATCHED"
INCONCLUSIVE = "INCONCLUSIVE"
OUTCOMES = (MATCH_CONFIRMED, CANDIDATE, NOT_MATCHED, INCONCLUSIVE)

OUTCOME_MEANING = {
    MATCH_CONFIRMED: "Strong, corroborated evidence that both files carry the same underlying content. "
                     "Requires human review; it is not a finding of misconduct.",
    CANDIDATE: "Some evidence of shared content or layout, but not enough (or conflicting) to confirm. Review the evidence.",
    NOT_MATCHED: "Examined and not considered shared content (for example the same template with different critical details).",
    INCONCLUSIVE: "The comparison could not be completed (unreadable, missing or unrenderable evidence).",
}

# Critical fields compared across cases, with how they are compared.
CRITICAL_FIELDS: dict[str, str] = {
    "institution_name": "name",
    "certificate_number": "identifier",
    "issue_date": "date",
    "noc_reference": "identifier",
    "structural_reference": "identifier",
    "survey_number": "identifier",
    "valid_until": "date",
    "trust_name": "name",
    "resolution_date": "date",
}


@dataclass(frozen=True)
class ReuseConfig:
    """Versioned thresholds. Changing any value requires a new ``version`` (pairs are keyed by it).

    Values were selected on the *development* fixture split only (see docs/reuse-detection.md) and frozen
    before the held-out split was evaluated.
    """

    version: str = "reuse_thr_v3"
    min_text_chars: int = 60
    shingle_size: int = 5
    text_candidate: float = 0.45  # L1 retrieval: Jaccard at or above → candidate
    text_strong: float = 0.85  # Jaccard or containment at or above → strong textual similarity
    text_unrelated: float = 0.35  # both texts readable and Jaccard below → body content differs
    phash_candidate: int = 12  # L2 retrieval: Hamming distance at or below → candidate (64-bit hash)
    min_page_ink: float = 0.004  # pages with less ink are skipped by L2 (blank / unreadable)
    min_inliers: int = 40
    min_inlier_ratio: float = 0.25
    min_coverage: float = 0.52
    max_diff_cells_for_identical: int = 0
    # v2: verified geometry with more localized difference regions than this is layout-only similarity.
    # Chosen from the dev split only (positives/alterations 0–1 regions, same-template negatives 7–17 → midpoint 4).
    max_diff_regions_shared: int = 4
    min_agreeing_fields: int = 2
    max_conflicts_alteration: int = 1  # ≤ this many conflicting fields on strong similarity → possible alteration
    # v3 (OCR): text whose OCR pages have a mean engine confidence below this is not used as strong evidence; a field
    # disagreement involving an OCR line below ``low_ocr_field_confidence`` is inconclusive (possible misread).
    low_ocr_text_confidence: float = 0.60
    low_ocr_field_confidence: float = 0.80
    max_pages: int = 10
    visual: visual.VisualParams = field(default_factory=visual.VisualParams)

    def snapshot(self) -> dict:
        data = asdict(self)
        data["engine_version"] = ENGINE_VERSION
        data["text_norm_version"] = TEXT_NORM_VERSION
        data["phash_version"] = visual.PHASH_VERSION
        data["geometric_version"] = visual.GEOMETRIC_VERSION
        data["field_compare_version"] = FIELD_COMPARE_VERSION
        data["fusion_version"] = FUSION_VERSION
        data["explanation_version"] = EXPLANATION_VERSION
        return data


DEFAULT_CONFIG = ReuseConfig()


def pipeline_version(config: ReuseConfig = DEFAULT_CONFIG) -> str:
    return (f"{ENGINE_VERSION}+{TEXT_NORM_VERSION}+{visual.PHASH_VERSION}+{visual.GEOMETRIC_VERSION}"
            f"+{FIELD_COMPARE_VERSION}+{FUSION_VERSION}")


# --- inputs --------------------------------------------------------------------------------------

@dataclass
class PageText:
    page_number: int
    text: str
    status: str = "ok"  # page status from processing (ok / too_little_text / failed …)
    method: str = "text_layer"  # text_layer / ocr / none
    ocr_confidence: float | None = None


@dataclass
class FieldEvidence:
    field_name: str
    raw_value: str | None
    normalized_value: dict | None
    page_number: int | None
    evidence_quote: str | None
    status: str  # extracted / not_found / ambiguous / unverified
    evidence_source: str | None = None  # text_layer / ocr
    evidence_box: list | None = None  # normalised [x0, y0, x1, y1] on the page
    ocr_confidence: float | None = None


@dataclass
class DocumentInput:
    ref: str  # opaque reference (document id or fixture id)
    case_ref: str  # application id or fixture case id
    sha256: str
    pdf_bytes: bytes
    pages: list[PageText]
    fields: list[FieldEvidence]
    text_status: str = "available"  # available / not_processed / failed
    _descriptors: list | None = None
    _descriptor_error: str | None = None
    _norm_text: str | None = None
    _shingles: set | None = None

    def descriptors(self, config: ReuseConfig):
        if self._descriptors is None:
            self._descriptors, self._descriptor_error = visual.describe_pages(self.pdf_bytes, config.visual, config.max_pages)
        return self._descriptors

    def normalized_text(self) -> str:
        if self._norm_text is None:
            self._norm_text = normalize_text("\n".join(p.text for p in self.pages))
        return self._norm_text

    def shingles(self, config: ReuseConfig) -> set:
        if self._shingles is None:
            text = re.sub(r"\s+", "", self.normalized_text())  # txtnorm_v2: whitespace-insensitive shingles
            k = config.shingle_size
            self._shingles = {text[i:i + k] for i in range(max(len(text) - k + 1, 0))}
        return self._shingles


_ZERO_WIDTH = re.compile("[­​‌‍⁠﻿]")


def normalize_text(text: str) -> str:
    """Conservative — keeps every letter, digit and punctuation mark (whitespace is dropped only for shingling)."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    return collapse_ws(text.casefold())


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


# --- stages --------------------------------------------------------------------------------------

def exact_stage(a: DocumentInput, b: DocumentInput) -> dict:
    return {"method": "sha256", "equal": a.sha256 == b.sha256, "sha256_a": a.sha256, "sha256_b": b.sha256,
            "note": "Byte identity only; does not establish authenticity or intent."}


def provenance(doc: DocumentInput) -> dict:
    ocr = [p for p in doc.pages if p.method == "ocr" and p.status == "ok"]
    confs = [p.ocr_confidence for p in ocr if p.ocr_confidence is not None]
    return {"text_layer_pages": sum(1 for p in doc.pages if p.method == "text_layer" and p.status == "ok"),
            "ocr_pages": len(ocr), "ocr_mean_confidence": round(sum(confs) / len(confs), 4) if confs else None,
            "unreadable_pages": sum(1 for p in doc.pages if p.status != "ok")}


def text_stage(a: DocumentInput, b: DocumentInput, config: ReuseConfig) -> dict:
    out = {"method": TEXT_METRIC, "normalization": TEXT_NORM_VERSION, "shingle_size": config.shingle_size,
           "provenance": {"a": provenance(a), "b": provenance(b)}}
    la, lb = len(a.normalized_text()), len(b.normalized_text())
    out.update(chars_a=la, chars_b=lb)
    reasons = []
    for side, doc, length in (("A", a, la), ("B", b, lb)):
        if doc.text_status == "not_processed":
            reasons.append(f"Document {side} has not been processed, so no text is available.")
        elif doc.text_status != "available":
            reasons.append(f"Text of document {side} could not be read (processing failed, e.g. image-only pages "
                           "without OCR).")
        elif length < config.min_text_chars:
            reasons.append(f"Document {side} has too little readable text ({length} characters; OCR unavailable or page unreadable).")
    if reasons:
        return {**out, "status": "unavailable", "reason": " ".join(reasons)}
    sa, sb = a.shingles(config), b.shingles(config)
    inter = len(sa & sb)
    jaccard = inter / len(sa | sb)
    containment = inter / min(len(sa), len(sb))
    low = [side for side, pv in (("A", out["provenance"]["a"]), ("B", out["provenance"]["b"]))
           if pv["ocr_pages"] and pv["ocr_mean_confidence"] is not None
           and pv["ocr_mean_confidence"] < config.low_ocr_text_confidence]
    result = {**out, "status": "computed", "jaccard": round(jaccard, 4), "containment": round(containment, 4),
              "shared_shingles": inter, "shingles_a": len(sa), "shingles_b": len(sb), "low_quality": bool(low)}
    if low:
        result["quality_note"] = (f"Text of document {' and '.join(low)} was read by OCR with low confidence; "
                                  "it is reported but not used as strong evidence.")
    return result


def visual_stage(a: DocumentInput, b: DocumentInput, config: ReuseConfig) -> dict:
    da, db = a.descriptors(config), b.descriptors(config)
    out = {"method": visual.PHASH_VERSION, "metric": "hamming_distance_64bit", "render_dpi": config.visual.hash_dpi,
           "pages_a": len(da), "pages_b": len(db)}
    errors = [e for e in (a._descriptor_error, b._descriptor_error) if e]
    if errors:
        return {**out, "status": "unavailable", "reason": f"Page rendering failed: {', '.join(errors)}."}
    best = visual.best_page_match(da, db, config.min_page_ink)
    if best is None:
        return {**out, "status": "unavailable", "reason": "No page with enough visible content to compare."}
    return {**out, "status": "computed", **best, "similarity": round(1 - best["distance"] / 64, 4)}


def _field_map(doc: DocumentInput) -> dict[str, FieldEvidence]:
    return {f.field_name: f for f in doc.fields}


def _has_source(doc: DocumentInput, f: FieldEvidence) -> bool:
    if f.status != "extracted" or not f.page_number or not f.evidence_quote or f.raw_value is None:
        return False
    page = next((p for p in doc.pages if p.page_number == f.page_number), None)
    return page is not None and is_grounded(f.evidence_quote, page.text)


def _comparable(kind: str, f: FieldEvidence) -> str | None:
    norm = f.normalized_value or {}
    if kind == "date":
        return norm.get("date")  # ambiguous dates stay unnormalised → not comparable
    if kind == "identifier":
        return norm.get("text") or normalize_identifier(f.raw_value or "")
    # fieldcmp_v2: names compare ignoring whitespace (OCR often drops or inserts spaces).
    return re.sub(r"\s+", "", norm.get("text") or normalize_name(f.raw_value or ""))


def field_stage(a: DocumentInput, b: DocumentInput, config: ReuseConfig = None) -> dict:
    config = config or DEFAULT_CONFIG
    fa, fb = _field_map(a), _field_map(b)
    comparisons = []
    for name, kind in CRITICAL_FIELDS.items():
        xa, xb = fa.get(name), fb.get(name)
        if xa is None and xb is None:
            continue
        row = {"field": name, "kind": kind,
               "a": _field_view(xa), "b": _field_view(xb)}
        sa, sb = xa is not None and _has_source(a, xa), xb is not None and _has_source(b, xb)
        if not sa and not sb:
            if (xa is None or xa.status == "not_found") and (xb is None or xb.status == "not_found"):
                continue  # absent on both sides: nothing to compare
            row.update(outcome="inconclusive", explanation="Neither value has a grounded source; not compared.")
        elif not (sa and sb):
            missing = "B" if sa else "A"
            other = xb if sa else xa
            why = "not found" if other is None or other.status == "not_found" else (other.status if other else "absent")
            row.update(outcome="inconclusive",
                       explanation=f"Value on side {missing} is {why}; a missing or unreadable value is not a conflict.")
        else:
            ca, cb = _comparable(kind, xa), _comparable(kind, xb)
            row["normalized"] = {"a": ca, "b": cb}
            if ca is None or cb is None:
                row.update(outcome="inconclusive", explanation="A value could not be normalised safely (e.g. ambiguous date).")
            elif ca == cb:
                row.update(outcome="agree", explanation="Same value after conservative normalisation.")
            elif any(x.evidence_source == "ocr" and x.ocr_confidence is not None
                     and x.ocr_confidence < config.low_ocr_field_confidence for x in (xa, xb)):
                row.update(outcome="inconclusive",
                           explanation="Values differ, but at least one was read by OCR with low confidence; this may be "
                                       "a misread, so it is not treated as a conflict.")
            else:
                row.update(outcome="conflict",
                           explanation="Different values with grounded evidence on both sides. A discrepancy for review, "
                                       "not a conclusion about intent.")
        comparisons.append(row)
    counts = {k: sum(1 for c in comparisons if c["outcome"] == k) for k in ("agree", "conflict", "inconclusive")}
    return {"method": FIELD_COMPARE_VERSION, "comparisons": comparisons, **counts,
            "note": "Only extracted values whose quote is grounded in the stored page text are compared."}


def _field_view(f: FieldEvidence | None) -> dict | None:
    if f is None:
        return None
    return {"raw_value": f.raw_value, "page_number": f.page_number, "evidence_quote": f.evidence_quote, "status": f.status,
            "evidence_source": f.evidence_source, "evidence_box": f.evidence_box, "ocr_confidence": f.ocr_confidence}


def is_text_candidate(t: dict, config: ReuseConfig) -> bool:
    return t.get("status") == "computed" and t["jaccard"] >= config.text_candidate


def is_visual_candidate(v: dict, config: ReuseConfig) -> bool:
    return v.get("status") == "computed" and v["distance"] <= config.phash_candidate


# --- decision ------------------------------------------------------------------------------------

def finalize_geometry(g: dict | None, config: ReuseConfig) -> dict | None:
    if not g or g.get("status") != "candidate_geometry":
        return g
    ok = (g["inliers"] >= config.min_inliers and g["inlier_ratio"] >= config.min_inlier_ratio
          and g["coverage"] >= config.min_coverage)
    g = dict(g)
    g["status"] = "verified" if ok else "not_verified"
    g["thresholds"] = {"min_inliers": config.min_inliers, "min_inlier_ratio": config.min_inlier_ratio,
                       "min_coverage": config.min_coverage}
    if not ok:
        g["reason"] = "Correspondences did not meet the inlier, ratio and coverage thresholds."
    return g


def decide(exact: dict, text: dict, vis: dict, geo: dict | None, fields: dict, config: ReuseConfig) -> tuple[str, list[str], list[str]]:
    """(outcome, reasons surfaced, uncertainties)."""
    reasons: list[str] = []
    unc: list[str] = []
    if exact["equal"]:
        return MATCH_CONFIRMED, ["Rule: identical file bytes (SHA-256)."], ["Byte identity says nothing about authenticity or intent."]

    text_ok = text.get("status") == "computed" and not text.get("low_quality")
    strong_text = text_ok and max(text["jaccard"], text["containment"]) >= config.text_strong
    unrelated_text = text_ok and text["jaccard"] < config.text_unrelated
    geo_verified = bool(geo and geo.get("status") == "verified")
    diffs = (geo or {}).get("differences") or {}
    geo_identical = geo_verified and diffs.get("cells_different", 1) <= config.max_diff_cells_for_identical
    conflicts, agrees = fields["conflict"], fields["agree"]

    if text_ok:
        reasons.append(f"Text similarity: Jaccard {text['jaccard']}, containment {text['containment']}.")
    elif text.get("status") == "computed":
        unc.append(text.get("quality_note", "Text quality too low to rely on."))
    else:
        unc.append(text.get("reason", "Text comparison unavailable."))
    if vis.get("status") == "computed":
        reasons.append(f"Best page pHash distance {vis['distance']}/64 (page {vis['page_a']} vs {vis['page_b']}"
                       f"{', B rotated ' + str(vis['rotation_b_degrees']) + '°' if vis['rotation_b_degrees'] else ''}).")
    else:
        unc.append(vis.get("reason", "Visual comparison unavailable."))
    if geo:
        if geo.get("status") in ("verified", "not_verified") and "inliers" in geo:
            reasons.append(f"Geometric verification {geo['status'].replace('_', ' ')}: {geo.get('inliers', 0)} inliers of "
                           f"{geo.get('tentative_matches', 0)} matches, coverage {geo.get('coverage', 0)}.")
            if geo_verified:
                reasons.append(f"Localized visual differences in {diffs.get('cells_different', 0)} of "
                               f"{diffs.get('cells_judged', 0)} content cells after alignment.")
        else:
            unc.append(geo.get("reason", "Geometric verification did not complete."))
    if conflicts:
        reasons.append(f"{conflicts} critical field(s) conflict.")
    if agrees:
        reasons.append(f"{agrees} critical field(s) agree.")
    if fields["inconclusive"]:
        unc.append(f"{fields['inconclusive']} critical field comparison(s) inconclusive (missing or unreadable values).")

    layout_only = geo_verified and diffs.get("cells_different", 0) > config.max_diff_regions_shared
    strong_visual = geo_verified and not layout_only
    if not text_ok and vis.get("status") != "computed":
        return INCONCLUSIVE, reasons + ["Rule: neither text nor page images could be compared."], unc

    # Readable, unrelated body text outweighs layout similarity and isolated field values (v2: checked first).
    if unrelated_text and not geo_identical:
        return NOT_MATCHED, reasons + ["Rule: readable body text differs; any visual similarity is limited to layout elements."], unc

    if conflicts:
        if (strong_text or strong_visual) and conflicts <= config.max_conflicts_alteration:
            return CANDIDATE, reasons + ["Rule: shared content or layout with a conflicting critical field: possible alteration, "
                                         "or a different document on the same layout. Requires review."], unc
        if strong_text or strong_visual:
            return NOT_MATCHED, reasons + ["Rule: similar template, but several critical fields differ."], unc
        return NOT_MATCHED, reasons + ["Rule: critical fields conflict and there is no strong evidence of shared content."], unc

    if strong_text and agrees >= config.min_agreeing_fields:
        return MATCH_CONFIRMED, reasons + ["Rule: strong text similarity corroborated by agreeing grounded critical fields."], unc
    if geo_identical and (strong_text or agrees >= config.min_agreeing_fields):
        return MATCH_CONFIRMED, reasons + ["Rule: aligned pages show no localized differences, corroborated by text or fields."], unc
    if geo_identical:
        if not text_ok:
            return CANDIDATE, reasons + ["Rule: pages align with no localized differences, but text and fields could not be "
                                         "read to corroborate (OCR unavailable, low quality or page unreadable)."], unc
        return CANDIDATE, reasons + ["Rule: pages align with no localized differences, but fewer than "
                                     f"{config.min_agreeing_fields} critical fields could be corroborated."], unc
    if layout_only and not strong_text:
        return NOT_MATCHED, reasons + [f"Rule: pages share a layout but differ in {diffs.get('cells_different')} regions; "
                                       "layout similarity alone is not shared content."], unc
    if strong_text or strong_visual:
        if strong_visual and diffs.get("cells_different"):
            return CANDIDATE, reasons + ["Rule: pages align but differ locally; inspect the highlighted regions."], unc
        return CANDIDATE, reasons + ["Rule: similarity without enough corroborating evidence to confirm."], unc
    if geo and geo.get("status") in ("inconclusive", "unavailable") and not text_ok:
        return INCONCLUSIVE, reasons + ["Rule: neither readable text nor verifiable geometry was available."], unc
    return NOT_MATCHED, reasons + ["Rule: similarity below the candidate thresholds after verification."], unc


# --- region-aware comparison ------------------------------------------------------------------------

def _overlap(a: list, b: list) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def annotate_regions(fields: dict, geo: dict | None) -> dict:
    """Map L3 difference regions (side A frame) onto side-A field evidence boxes. Adds ``visual_difference`` per
    comparison (True / False / None when no box or no verified alignment) and a summary."""
    regions = ((geo or {}).get("differences") or {}).get("regions") or []
    verified = bool(geo and geo.get("status") == "verified")
    on_fields = set()
    for c in fields["comparisons"]:
        box = (c.get("a") or {}).get("evidence_box")
        if not verified or not box:
            c["visual_difference"] = None
            continue
        hits = [i for i, r in enumerate(regions) if _overlap(r["box"], box)]
        c["visual_difference"] = bool(hits)
        on_fields.update(hits)
    return {"regions_total": len(regions), "regions_on_critical_fields": len(on_fields),
            "regions_elsewhere": len(regions) - len(on_fields), "alignment_verified": verified,
            "fields_with_visual_difference": [c["field"] for c in fields["comparisons"] if c.get("visual_difference")]}


# --- L4 fusion and explanation ---------------------------------------------------------------------

def fuse(outcome: str, exact: dict, text: dict, vis: dict, geo: dict | None, fields: dict, regions: dict,
         config: ReuseConfig, rule: str) -> dict:
    """Transparent record of how each signal bears on the outcome. ``ref`` is the evidence path that holds it."""
    supporting, contradicting, unavailable, neutral = [], [], [], []

    def add(bucket, signal, detail, ref):
        bucket.append({"signal": signal, "detail": detail, "ref": ref})

    if exact["equal"]:
        add(supporting, "exact_identity", "Identical SHA-256", "exact.equal")
    else:
        add(neutral, "exact_identity", "Different file bytes (expected for any transformed copy)", "exact.equal")
    if text.get("status") != "computed":
        add(unavailable, "text", text.get("reason", "Text unavailable"), "text.reason")
    elif text.get("low_quality"):
        add(unavailable, "text", text.get("quality_note", "Low-quality OCR text"), "text.quality_note")
    else:
        strong = max(text["jaccard"], text["containment"]) >= config.text_strong
        bucket = supporting if strong else contradicting if text["jaccard"] < config.text_unrelated else neutral
        add(bucket, "text", f"Jaccard {text['jaccard']}, containment {text['containment']}", "text.jaccard")
    if vis.get("status") == "computed":
        add(supporting if vis["distance"] <= config.phash_candidate else neutral, "visual_retrieval",
            f"pHash distance {vis['distance']}/64 (retrieval signal only)", "visual.distance")
    else:
        add(unavailable, "visual_retrieval", vis.get("reason", "Page images unavailable"), "visual.reason")
    if geo is None:
        pass
    elif geo.get("status") == "verified":
        add(supporting, "geometry", f"{geo['inliers']} inliers / {geo.get('tentative_matches', 0)} matches, coverage "
            f"{geo['coverage']}", "geometric.inliers")
        n = regions["regions_total"]
        if n == 0:
            add(supporting, "difference_regions", "No localized differences after alignment", "geometric.differences")
        elif n > config.max_diff_regions_shared:
            add(contradicting, "difference_regions", f"{n} localized difference regions: layout similarity only",
                "geometric.differences")
        else:
            add(neutral, "difference_regions", f"{n} localized difference region(s)", "geometric.differences")
        if regions["fields_with_visual_difference"]:
            add(contradicting, "field_regions", "Differences overlap the evidence of: "
                + ", ".join(f.replace("_", " ") for f in regions["fields_with_visual_difference"]),
                "fields.comparisons[].visual_difference")
    elif geo.get("status") == "not_verified":
        add(contradicting if "inliers" in geo else neutral, "geometry",
            geo.get("reason", "Not verified"), "geometric.status")
    else:
        add(unavailable, "geometry", geo.get("reason", "Geometric verification did not run"), "geometric.reason")
    for c in fields["comparisons"]:
        ref = f"fields.comparisons[{c['field']}]"
        if c["outcome"] == "agree":
            add(supporting, f"field:{c['field']}", "Agrees in grounded evidence", ref)
        elif c["outcome"] == "conflict":
            add(contradicting, f"field:{c['field']}", "Conflicts in grounded evidence", ref)
        else:
            add(unavailable, f"field:{c['field']}", c["explanation"], ref)
    pa, pb = (text.get("provenance") or {}).get("a", {}), (text.get("provenance") or {}).get("b", {})
    return {"version": FUSION_VERSION, "outcome": outcome, "rule": rule, "supporting": supporting,
            "contradicting": contradicting, "unavailable": unavailable, "neutral": neutral,
            "fields": {k: fields[k] for k in ("agree", "conflict", "inconclusive")},
            "regions": regions, "quality": {"a": pa, "b": pb},
            "note": "Rule-based and transparent; a matching outcome is not a compliance, authenticity or misconduct finding."}


def explain(fusion: dict, exact: dict, text: dict, vis: dict, geo: dict | None, fields: dict) -> dict:
    """Concise reviewer statements generated only from stored evidence. Each statement lists the evidence paths
    and values it relies on, so it can be traced (and tested) against the record."""
    out = []

    def say(kind, text_, refs):
        out.append({"kind": kind, "text": text_, "refs": refs})

    if exact["equal"]:
        say("supports", "The two files are byte-identical (same SHA-256).", {"exact.equal": True})
    if geo and geo.get("status") == "verified":
        n = fusion["regions"]["regions_total"]
        say("supports" if n <= 4 else "contradicts",
            f"After geometric alignment ({geo['inliers']} inliers, coverage {geo['coverage']}), "
            + ("no localized differences were found." if n == 0 else f"{n} localized difference region(s) remain."),
            {"geometric.inliers": geo["inliers"], "geometric.coverage": geo["coverage"], "geometric.differences.cells_different": n})
    elif geo and geo.get("status") in ("not_verified", "inconclusive", "unavailable"):
        say("contradicts" if geo.get("status") == "not_verified" else "unavailable",
            f"Geometric verification {geo['status'].replace('_', ' ')}: {geo.get('reason', '')}".strip(),
            {"geometric.status": geo["status"]})
    if text.get("status") == "computed" and not text.get("low_quality"):
        say("supports" if max(text["jaccard"], text["containment"]) >= 0.85 else "neutral",
            f"Text similarity is {text['jaccard']} (Jaccard) / {text['containment']} (containment).",
            {"text.jaccard": text["jaccard"], "text.containment": text["containment"]})
    elif text.get("status") == "computed":
        say("unavailable", text.get("quality_note", ""), {"text.low_quality": True})
    else:
        say("unavailable", f"Text-level evidence could not be evaluated: {text.get('reason', '')}", {"text.status": text.get("status")})
    for c in fields["comparisons"]:
        name = c["field"].replace("_", " ")
        a, b = c.get("a") or {}, c.get("b") or {}
        if c["outcome"] == "agree":
            say("supports", f"The {name} agrees: “{a.get('raw_value')}” (page {a.get('page_number')}) in both documents.",
                {f"fields[{c['field']}].a.raw_value": a.get("raw_value"), f"fields[{c['field']}].a.page_number": a.get("page_number")})
        elif c["outcome"] == "conflict":
            extra = " The aligned images also differ at that line." if c.get("visual_difference") else ""
            say("contradicts", f"The {name} differs: “{a.get('raw_value')}” (A, page {a.get('page_number')}) vs "
                f"“{b.get('raw_value')}” (B, page {b.get('page_number')}).{extra}",
                {f"fields[{c['field']}].a.raw_value": a.get("raw_value"), f"fields[{c['field']}].b.raw_value": b.get("raw_value")})
    if fields["inconclusive"]:
        say("unavailable", f"{fields['inconclusive']} critical field(s) could not be compared (missing, unreadable or "
            "low-confidence values).", {"fields.inconclusive": fields["inconclusive"]})
    return {"version": EXPLANATION_VERSION, "generator": "deterministic", "statements": out,
            "rule": fusion["rule"],
            "disclaimer": "Generated from the stored evidence record, which remains authoritative. Not a finding of misconduct."}


def _rule_for(outcome: str, reasons: list[str]) -> str:
    rules = [r for r in reasons if r.startswith("Rule: ")]
    return rules[-1][len("Rule: "):] if rules else outcome


@dataclass
class PairResult:
    outcome: str
    candidate_methods: list[str]
    candidate_score: float | None
    exact: dict
    text: dict
    visual: dict
    geometric: dict | None
    fields: dict
    matched_pages: list[dict]
    reasons: list[str]
    uncertainties: list[str]
    stage_status: dict
    latency_ms: float
    fusion: dict | None = None
    explanation: dict | None = None


def is_candidate(a: DocumentInput, b: DocumentInput, config: ReuseConfig = DEFAULT_CONFIG) -> tuple[list[str], dict, dict, dict]:
    """Cheap retrieval (L0–L2). Returns (methods that surfaced the pair, exact, text, visual)."""
    ex = exact_stage(a, b)
    tx = text_stage(a, b, config)
    vi = visual_stage(a, b, config)
    methods = []
    if ex["equal"]:
        methods.append("exact_sha256")
    if is_text_candidate(tx, config):
        methods.append("text_shingles")
    if is_visual_candidate(vi, config):
        methods.append("visual_phash")
    return methods, ex, tx, vi


def compare(a: DocumentInput, b: DocumentInput, config: ReuseConfig = DEFAULT_CONFIG, *,
            retrieval: tuple | None = None) -> PairResult:
    """Full cascade for one document pair (call after retrieval surfaced it, or directly for evaluation)."""
    started = time.perf_counter()
    methods, ex, tx, vi = retrieval or is_candidate(a, b, config)
    geo = None
    if not ex["equal"] and vi.get("status") == "computed":
        geo = finalize_geometry(visual.geometric_verify(a.pdf_bytes, vi["page_a"], b.pdf_bytes, vi["page_b"],
                                                        config.visual), config)
    elif not ex["equal"]:
        geo = {"method": visual.GEOMETRIC_VERSION, "status": "inconclusive",
               "reason": "No renderable page pair to verify."}
    fl = field_stage(a, b, config)
    regions = annotate_regions(fl, geo)
    outcome, reasons, unc = decide(ex, tx, vi, geo, fl, config)
    fusion = fuse(outcome, ex, tx, vi, geo, fl, regions, config, _rule_for(outcome, reasons))
    matched_pages = []
    if vi.get("status") == "computed":
        matched_pages.append({"page_a": vi["page_a"], "page_b": vi["page_b"], "basis": "best pHash page pair",
                              "rotation_b_degrees": vi["rotation_b_degrees"]})
    score = None
    if tx.get("status") == "computed" or vi.get("status") == "computed":
        score = round(max(tx.get("jaccard", 0.0), vi.get("similarity", 0.0)), 4)
    stage_status = {"exact": "computed", "text": tx.get("status") if not tx.get("low_quality") else "low_quality_ocr",
                    "visual": vi.get("status"), "geometric": (geo or {}).get("status", "not_needed"), "fields": "computed",
                    "fusion": FUSION_VERSION}
    return PairResult(outcome, methods, score, ex, tx, vi, geo, fl, matched_pages, reasons, unc, stage_status,
                      round((time.perf_counter() - started) * 1000, 1), fusion,
                      explain(fusion, ex, tx, vi, geo, fl))
