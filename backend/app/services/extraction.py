"""Deterministic, evidence-grounded field extraction (method ``label_regex_v1``).

A field is found only where the page text contains an explicit label followed by a separator and a value on
the same line, e.g. ``Valid Until: 13 March 2029``. The evidence quote is that whole line, and it must occur
in the stored page text (whitespace-normalised) or the field is marked ``unverified``. Nothing is inferred:
no validity periods, no default authorities, no guessed identifiers.

Confidence (qualitative): high = labelled value on a text-layer page that normalised cleanly;
medium = labelled value on an OCR page; low = value that could not be normalised (e.g. unknown unit).
Status: extracted | not_found | ambiguous (several different values, or an ambiguous date) | unverified.
An optional local-model extractor could later implement the same ``FieldResult`` contract.
"""

import re
from dataclasses import dataclass, field

from app.models.enums import Confidence, DocumentCategory as C, FieldStatus, PageExtractionMethod
from app.services.normalize import collapse_ws, is_grounded, normalize_identifier, normalize_name, parse_area, parse_date

EXTRACTOR_VERSION = "label_regex_v1"
MAX_VALUE_LEN = 200


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str  # regex alternation for the label
    kind: str  # text | name | identifier | date | area


SPECS: list[FieldSpec] = [
    FieldSpec("institution_name", r"name\s+of\s+(?:the\s+)?(?:institution|institute|college)|institution\s+name|issued\s+to", "name"),
    FieldSpec("trust_name", r"name\s+of\s+(?:the\s+)?(?:trust|society)(?:\s*/\s*society)?|trust\s*/\s*society|sponsoring\s+body", "name"),
    FieldSpec("certificate_number", r"(?:certificate|cert\.?)\s*(?:no\.?|number|#)", "identifier"),
    FieldSpec("noc_reference", r"noc\s*(?:ref(?:erence)?\.?\s*)?(?:no\.?|number)|noc\s+reference", "identifier"),
    FieldSpec("structural_reference", r"structural\s+(?:stability\s+)?report\s*(?:ref(?:erence)?\.?|no\.?)", "identifier"),
    FieldSpec("issuing_authority", r"issuing\s+authority|issued\s+by", "name"),
    FieldSpec("issue_date", r"date\s+of\s+issue|issue\s+date|issued\s+on", "date"),
    FieldSpec("valid_until", r"valid\s+(?:until|upto|up\s+to|till)|validity\s+(?:upto|up\s+to|until|till)|expiry\s+date|date\s+of\s+expiry|expires\s+on", "date"),
    FieldSpec("property_identifier", r"property\s*(?:id|identifier|no\.?|number)", "identifier"),
    FieldSpec("survey_number", r"survey\s*(?:no\.?|number)", "identifier"),
    FieldSpec("plot_number", r"plot\s*(?:no\.?|number)", "identifier"),
    FieldSpec("address", r"address(?:\s+of\s+(?:the\s+)?premises)?|location|situated\s+at", "text"),
    FieldSpec("built_up_area", r"(?:total\s+)?built[\s-]*up\s+area|total\s+floor\s+area|floor\s+area", "area"),
    FieldSpec("university_name", r"name\s+of\s+(?:the\s+)?university|affiliating\s+university|university\s+name", "name"),
    FieldSpec("resolution_date", r"date\s+of\s+(?:the\s+)?resolution|resolution\s+date", "date"),
]
SPEC_BY_NAME = {s.name: s for s in SPECS}
FIELD_NAMES = tuple(SPEC_BY_NAME)

COMMON = ["institution_name", "certificate_number", "issuing_authority", "issue_date", "address"]
FIELDS_BY_CATEGORY: dict[C, list[str]] = {
    C.FIRE_SAFETY_CERTIFICATE: COMMON + ["valid_until", "survey_number"],
    C.OCCUPANCY_CERTIFICATE: COMMON + ["survey_number", "built_up_area"],
    C.COMPLETION_CERTIFICATE: COMMON + ["survey_number", "built_up_area"],
    C.BUILDING_LICENSE: COMMON + ["valid_until", "survey_number", "built_up_area"],
    C.FORM_D: COMMON + ["valid_until", "survey_number", "built_up_area"],
    C.STRUCTURAL_STABILITY_CERTIFICATE: COMMON + ["structural_reference", "valid_until"],
    C.BUILDING_PLAN: ["institution_name", "issuing_authority", "issue_date", "address", "survey_number",
                      "plot_number", "built_up_area"],
    C.UNIVERSITY_NOC: ["institution_name", "university_name", "noc_reference", "issue_date", "address"],
    C.TRUST_RESOLUTION: ["trust_name", "institution_name", "resolution_date"],
    C.OTHER: COMMON,
}

_PATTERNS = {
    s.name: re.compile(rf"^[ \t]*(?:{s.label})[ \t]*(?:[:\-–—]|\.\s*:)[ \t]*(?P<value>\S[^\n]*?)[ \t]*$", re.I | re.M)
    for s in SPECS
}


@dataclass
class PageInput:
    page_number: int
    text: str
    method: PageExtractionMethod


@dataclass
class FieldResult:
    field_name: str
    raw_value: str | None
    normalized_value: dict | None
    page_number: int | None
    evidence_quote: str | None
    method: str
    confidence: Confidence
    status: FieldStatus
    warnings: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)


def _normalize(kind: str, raw: str) -> tuple[dict | None, list[str], bool]:
    """(normalized, warnings, ambiguous)."""
    if kind == "date":
        parsed = parse_date(raw)
        if parsed.iso:
            return {"date": parsed.iso}, [], False
        return None, [f"Date kept as written ('{raw}'): {parsed.note}"], parsed.ambiguous
    if kind == "area":
        area = parse_area(raw)
        if area.value_sq_m is not None:
            return {"value": area.value, "unit": area.unit, "value_sq_m": area.value_sq_m}, [], False
        return ({"value": area.value, "unit": None, "value_sq_m": None} if area.value is not None else None,
                [area.note or "Area could not be normalised."], False)
    if kind == "identifier":
        return {"text": normalize_identifier(raw)}, [], False
    if kind == "name":
        return {"text": normalize_name(raw)}, [], False
    return {"text": collapse_ws(raw)}, [], False


def _comparable(kind: str, raw: str, normalized: dict | None) -> str:
    if normalized:
        for key in ("date", "value_sq_m", "text"):
            if normalized.get(key) is not None:
                return str(normalized[key])
    return normalize_name(raw) if kind != "identifier" else normalize_identifier(raw)


def extract_fields(pages: list[PageInput], categories: set[C]) -> list[FieldResult]:
    """Extract every field relevant to ``categories`` (reported even when not found) plus any other
    field that is explicitly present."""
    wanted = {name for cat in categories for name in FIELDS_BY_CATEGORY.get(cat, COMMON)}
    results: list[FieldResult] = []
    for spec in SPECS:
        occurrences = []
        for page in pages:
            for m in _PATTERNS[spec.name].finditer(page.text):
                value = m.group("value").strip().rstrip(".;,").strip()[:MAX_VALUE_LEN]
                if value:
                    occurrences.append((page, m.group(0).strip(), value))
        if not occurrences:
            if spec.name in wanted:
                results.append(FieldResult(spec.name, None, None, None, None, EXTRACTOR_VERSION, Confidence.LOW,
                                           FieldStatus.NOT_FOUND, ["No labelled value found in the readable text."]))
            continue
        results.append(_build(spec, occurrences))
    return results


def _build(spec: FieldSpec, occurrences: list) -> FieldResult:
    distinct: dict[str, tuple] = {}
    for page, quote, value in occurrences:
        normalized, _, _ = _normalize(spec.kind, value)
        distinct.setdefault(_comparable(spec.kind, value, normalized), (page, quote, value))
    page, quote, value = occurrences[0]
    normalized, warnings, ambiguous_value = _normalize(spec.kind, value)
    candidates = [{"value": v, "page_number": p.page_number, "evidence_quote": q} for p, q, v in distinct.values()]

    status = FieldStatus.EXTRACTED
    if len(distinct) > 1:
        status = FieldStatus.AMBIGUOUS
        warnings = warnings + [f"{len(distinct)} different values found for this field; review the candidates."]
    elif ambiguous_value:
        status = FieldStatus.AMBIGUOUS
    if not is_grounded(quote, page.text):
        status = FieldStatus.UNVERIFIED
        warnings = warnings + ["The evidence quote could not be matched to the stored page text."]

    if page.method == PageExtractionMethod.OCR:
        confidence = Confidence.MEDIUM
        warnings = warnings + ["Value read from OCR text; recognition errors are possible."]
    elif normalized is None or (spec.kind == "area" and normalized.get("value_sq_m") is None):
        confidence = Confidence.LOW
    else:
        confidence = Confidence.HIGH
    return FieldResult(spec.name, value, normalized, page.page_number, quote, EXTRACTOR_VERSION, confidence, status,
                       warnings, candidates if len(distinct) > 1 else [])
