"""Conservative normalisation for comparisons. Original values are always kept separately.

Dates: only unambiguous dates are normalised. Numeric dates are read day-first (Indian convention) only when
the day part is > 12 or equals the month; otherwise (e.g. 05/06/2026) they are ambiguous and left unnormalised.
Areas: square metres and square feet are recognised; 1 sq ft = 0.09290304 sq m (exact definition).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

_WS = re.compile(r"\s+")


def collapse_ws(text: str) -> str:
    """Whitespace normalisation used for grounding: any run of whitespace becomes one space; ends trimmed."""
    return _WS.sub(" ", text).strip()


def is_grounded(quote: str | None, page_text: str) -> bool:
    """True if the quote occurs in the page text, ignoring only whitespace differences."""
    if not quote:
        return False
    return collapse_ws(quote) in collapse_ws(page_text)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = collapse_ws(text)
    return text[4:] if text.startswith("the ") else text


def text_similarity(a: str, b: str) -> float:
    """0..1. Max of character-sequence ratio and token containment of the shorter text in the longer."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    containment = len(shorter & longer) / len(shorter) if shorter else 0.0
    return round(max(ratio, containment), 4)


def normalize_identifier(value: str) -> str:
    """Uppercase; drop spaces, dots, hyphens and underscores. Slashes are kept (101/2A ≠ 1012A)."""
    text = unicodedata.normalize("NFKC", value).upper()
    text = re.sub(r"^(?:S\s*\.\s*NO|SURVEY\s*NO|PLOT\s*NO)\b\s*[.:]?\s*", "", text)
    return re.sub(r"[\s.\-_]", "", text)


# --- Dates ---------------------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


@dataclass
class ParsedDate:
    iso: str | None
    ambiguous: bool
    note: str | None = None


def _month(token: str) -> int | None:
    return _MONTHS.get(token[:3].lower()) if token[:3].isalpha() else None


def _safe_date(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_date(raw: str) -> ParsedDate:
    text = collapse_ws(raw).rstrip(".,;")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        iso = _safe_date(int(m[1]), int(m[2]), int(m[3]))
        return ParsedDate(iso, False, None if iso else "Not a valid calendar date.")
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})\.?,?[\s\-]+(\d{4})", text)
    if m and _month(m[2]):
        iso = _safe_date(int(m[3]), _month(m[2]), int(m[1]))
        return ParsedDate(iso, False, None if iso else "Not a valid calendar date.")
    m = re.fullmatch(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", text)
    if m and _month(m[1]):
        iso = _safe_date(int(m[3]), _month(m[1]), int(m[2]))
        return ParsedDate(iso, False, None if iso else "Not a valid calendar date.")
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", text)
    if m:
        first, second, year = int(m[1]), int(m[2]), int(m[3])
        if first > 12 or first == second:
            iso = _safe_date(year, second, first)
            return ParsedDate(iso, False, None if iso else "Not a valid calendar date.")
        if second > 12:
            # Month-first is the only valid reading; unusual for Indian documents, so flag it.
            return ParsedDate(None, True, "Only a month-first reading is valid; date order is uncertain.")
        return ParsedDate(None, True, "Numeric date could be read day-first or month-first.")
    return ParsedDate(None, True, "Date format not recognised.")


# --- Areas ---------------------------------------------------------------------------------------

SQ_FT_TO_SQ_M = 0.09290304
_UNITS = [
    (re.compile(r"^(?:sq\.?\s*m(?:etres?|eters?|trs?)?|square\s+m(?:etres?|eters?)|m2|m²)$", re.I), "sq_m"),
    (re.compile(r"^(?:sq\.?\s*f(?:ee)?t\.?|square\s+f(?:ee|oo)t|ft2|ft²)$", re.I), "sq_ft"),
]


@dataclass
class ParsedArea:
    value: float | None
    unit: str | None
    value_sq_m: float | None
    note: str | None = None


def parse_area(raw: str) -> ParsedArea:
    m = re.match(r"^\s*([\d,]+(?:\.\d+)?)\s*(.*?)\s*\.?\s*$", raw)
    if not m:
        return ParsedArea(None, None, None, "No numeric area value found.")
    try:
        value = float(m[1].replace(",", ""))
    except ValueError:
        return ParsedArea(None, None, None, "Area value is not a number.")
    unit_text = m[2].strip().rstrip(".")
    for pattern, unit in _UNITS:
        if unit_text and pattern.match(unit_text):
            sq_m = value if unit == "sq_m" else round(value * SQ_FT_TO_SQ_M, 3)
            return ParsedArea(value, unit, sq_m)
    return ParsedArea(value, None, None, "Area unit missing or not recognised; not converted.")
