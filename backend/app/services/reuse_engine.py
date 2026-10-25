"""Cross-case document reuse cascade (pure; no database access).

Stages, each reporting its raw metric, method and version:

* **L0 exact** — SHA-256 equality. Establishes byte identity only.
* **L1 text** — ``txtnorm_v1`` normalisation (NFKC, zero-width/soft-hyphen removal, casefold, whitespace runs →
  one space; no punctuation, digits or identifiers removed) and character 5-gram shingles. Raw metrics: Jaccard
  similarity and containment (shared shingles / smaller set). Texts below ``min_text_chars`` are *unavailable*,
  never a match — two empty texts are not evidence of anything.
* **L2 visual** — page pHash with rotation variants (see ``reuse_visual``); best Hamming distance.
* **L3 geometric** — ORB + RANSAC homography on the best-matching page pair, with a residual difference map.
* **Fields** — critical fields compared only when both sides were extracted with a quote grounded in the page
  text (a valid source pointer). Missing, ambiguous or unverified values are *inconclusive*, never a conflict.

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

ENGINE_VERSION = "reuse_cascade_v2"
TEXT_NORM_VERSION = "txtnorm_v1"
TEXT_METRIC = "char5_shingle_jaccard+containment"
FIELD_COMPARE_VERSION = "fieldcmp_v1"

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

    version: str = "reuse_thr_v2"
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
    max_pages: int = 10
    visual: visual.VisualParams = field(default_factory=visual.VisualParams)

    def snapshot(self) -> dict:
        data = asdict(self)
        data["engine_version"] = ENGINE_VERSION
        data["text_norm_version"] = TEXT_NORM_VERSION
        data["phash_version"] = visual.PHASH_VERSION
        data["geometric_version"] = visual.GEOMETRIC_VERSION
        data["field_compare_version"] = FIELD_COMPARE_VERSION
        return data


DEFAULT_CONFIG = ReuseConfig()


def pipeline_version(config: ReuseConfig = DEFAULT_CONFIG) -> str:
    return f"{ENGINE_VERSION}+{TEXT_NORM_VERSION}+{visual.PHASH_VERSION}+{visual.GEOMETRIC_VERSION}+{FIELD_COMPARE_VERSION}"


# --- inputs --------------------------------------------------------------------------------------

@dataclass
class PageText:
    page_number: int
    text: str
    status: str = "ok"  # page status from processing (ok / too_little_text / failed …)


@dataclass
class FieldEvidence:
    field_name: str
    raw_value: str | None
    normalized_value: dict | None
    page_number: int | None
    evidence_quote: str | None
    status: str  # extracted / not_found / ambiguous / unverified


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
            text = self.normalized_text()
            k = config.shingle_size
            self._shingles = {text[i:i + k] for i in range(max(len(text) - k + 1, 0))}
        return self._shingles


_ZERO_WIDTH = re.compile("[­​‌‍⁠﻿]")


def normalize_text(text: str) -> str:
    """``txtnorm_v1``: conservative — keeps every letter, digit and punctuation mark."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    return collapse_ws(text.casefold())


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


# --- stages --------------------------------------------------------------------------------------

def exact_stage(a: DocumentInput, b: DocumentInput) -> dict:
    return {"method": "sha256", "equal": a.sha256 == b.sha256, "sha256_a": a.sha256, "sha256_b": b.sha256,
            "note": "Byte identity only; does not establish authenticity or intent."}


def text_stage(a: DocumentInput, b: DocumentInput, config: ReuseConfig) -> dict:
    out = {"method": TEXT_METRIC, "normalization": TEXT_NORM_VERSION, "shingle_size": config.shingle_size}
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
    return {**out, "status": "computed", "jaccard": round(jaccard, 4), "containment": round(containment, 4),
            "shared_shingles": inter, "shingles_a": len(sa), "shingles_b": len(sb)}


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
    return norm.get("text") or normalize_name(f.raw_value or "")


def field_stage(a: DocumentInput, b: DocumentInput) -> dict:
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
    return {"raw_value": f.raw_value, "page_number": f.page_number, "evidence_quote": f.evidence_quote, "status": f.status}


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
        return MATCH_CONFIRMED, ["Identical file bytes (SHA-256)."], ["Byte identity says nothing about authenticity or intent."]

    text_ok = text.get("status") == "computed"
    strong_text = text_ok and max(text["jaccard"], text["containment"]) >= config.text_strong
    unrelated_text = text_ok and text["jaccard"] < config.text_unrelated
    geo_verified = bool(geo and geo.get("status") == "verified")
    diffs = (geo or {}).get("differences") or {}
    geo_identical = geo_verified and diffs.get("cells_different", 1) <= config.max_diff_cells_for_identical
    conflicts, agrees = fields["conflict"], fields["agree"]

    if text_ok:
        reasons.append(f"Text similarity: Jaccard {text['jaccard']}, containment {text['containment']}.")
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
        return INCONCLUSIVE, reasons, unc + ["Neither text nor page images could be compared."]

    # Readable, unrelated body text outweighs layout similarity and isolated field values (v2: checked first).
    if unrelated_text and not geo_identical:
        return NOT_MATCHED, reasons + ["Readable body text differs; any visual similarity is limited to layout elements."], unc

    if conflicts:
        if (strong_text or strong_visual) and conflicts <= config.max_conflicts_alteration:
            return CANDIDATE, reasons + ["Shared content or layout with a conflicting critical field: possible alteration, "
                                         "or a different document on the same layout. Requires review."], unc
        if strong_text or strong_visual:
            return NOT_MATCHED, reasons + ["Similar template, but several critical fields differ."], unc
        return NOT_MATCHED, reasons, unc

    if strong_text and agrees >= config.min_agreeing_fields:
        return MATCH_CONFIRMED, reasons + ["Strong text similarity corroborated by agreeing grounded critical fields."], unc
    if geo_identical and (strong_text or agrees >= config.min_agreeing_fields):
        return MATCH_CONFIRMED, reasons + ["Aligned pages show no localized differences, corroborated by text or fields."], unc
    if geo_identical:
        if not text_ok:
            return CANDIDATE, reasons + ["Pages align with no localized differences, but text and fields could not be read "
                                         "to corroborate (OCR unavailable or page unreadable)."], unc
        return CANDIDATE, reasons + ["Pages align with no localized differences, but fewer than "
                                     f"{config.min_agreeing_fields} critical fields could be corroborated."], unc
    if layout_only and not strong_text:
        return NOT_MATCHED, reasons + [f"Pages share a layout but differ in {diffs.get('cells_different')} regions; "
                                       "layout similarity alone is not shared content."], unc
    if strong_text or strong_visual:
        if strong_visual and diffs.get("cells_different"):
            return CANDIDATE, reasons + ["Pages align but differ locally; inspect the highlighted regions."], unc
        return CANDIDATE, reasons + ["Similarity without enough corroborating evidence to confirm."], unc
    if geo and geo.get("status") in ("inconclusive", "unavailable") and not text_ok:
        return INCONCLUSIVE, reasons, unc
    return NOT_MATCHED, reasons + ["Similarity below the candidate thresholds after verification."], unc


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
    fl = field_stage(a, b)
    outcome, reasons, unc = decide(ex, tx, vi, geo, fl, config)
    matched_pages = []
    if vi.get("status") == "computed":
        matched_pages.append({"page_a": vi["page_a"], "page_b": vi["page_b"], "basis": "best pHash page pair",
                              "rotation_b_degrees": vi["rotation_b_degrees"]})
    score = None
    if tx.get("status") == "computed" or vi.get("status") == "computed":
        score = round(max(tx.get("jaccard", 0.0), vi.get("similarity", 0.0)), 4)
    stage_status = {"exact": "computed", "text": tx.get("status"), "visual": vi.get("status"),
                    "geometric": (geo or {}).get("status", "not_needed"), "fields": "computed"}
    return PairResult(outcome, methods, score, ex, tx, vi, geo, fl, matched_pages, reasons, unc, stage_status,
                      round((time.perf_counter() - started) * 1000, 1))
