"""Pinned regulatory source (AICTE Approval Process Handbook) and the rule registry view built on it.

The manifest (``app/regulatory/aph_2024_27.json``) pins one exact PDF by URL and SHA-256 and lists the verified
passages that rules cite. Runtime checks use only the manifest and the versioned rules in code — the PDF is never
needed at run time and nothing is extracted from it automatically into policy. ``verify_pdf`` re-checks a local copy
of the PDF against the manifest (hash, page labels, every quotation).

Rule classification (registry view; derived from existing rule fields, not a new database enum):

* ``SOURCE_VERIFIED``    — quote verified in the pinned source and the logic restates it without interpretation.
* ``PARTIALLY_VERIFIED`` — quote verified, but applicability, dates or a cross-reference involve interpretation.
* ``UNRESOLVED``         — cited text could not be verified in the pinned source.
* ``DEMO_ONLY``          — prototype expectation with no handbook citation.
* ``RETIRED``            — kept for history; never evaluated.
* ``INTEGRITY_CHECK``    — a generic consistency check, not a regulatory rule.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "regulatory" / "aph_2024_27.json"


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def passage(passage_id: str) -> dict:
    return next(p for p in manifest()["passages"] if p["passage_id"] == passage_id)


def verify_pdf(path: Path) -> dict:
    """Check a local copy of the handbook against the manifest. Returns a report; raises nothing."""
    import pymupdf

    m = manifest()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    report = {"path": str(path), "sha256": digest, "sha256_matches": digest == m["sha256"],
              "bytes": len(data), "passages": [], "page_labels": []}
    if not report["sha256_matches"]:
        report["status"] = "different_file"
        return report
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        report["pdf_page_count"] = doc.page_count
        for entry in m["page_map"]:
            head = doc[entry["pdf_page"] - 1].get_text().splitlines()[:4]
            report["page_labels"].append({**entry, "found": any(line.strip() == entry["printed_page"] for line in head)})
        for p in m["passages"]:
            text = doc[p["pdf_page"] - 1].get_text()
            ok = p["quote"] in text
            hash_ok = "quote_sha256" not in p or hashlib.sha256(p["quote"].encode("utf-8")).hexdigest() == p["quote_sha256"]
            report["passages"].append({"passage_id": p["passage_id"], "quote_found": ok, "quote_hash_ok": hash_ok})
    report["status"] = "verified" if all(x["quote_found"] and x["quote_hash_ok"] for x in report["passages"]) \
        and all(x["found"] for x in report["page_labels"]) else "mismatch"
    return report


def classify(rule) -> str:
    """Registry classification for a DB scrutiny rule or an APH demo rule."""
    if getattr(rule, "classification", None):
        return rule.classification
    if getattr(rule, "retired", False):
        return "RETIRED"
    status = getattr(getattr(rule, "source_verification_status", None), "value", None)
    if status == "not_applicable":
        return "INTEGRITY_CHECK"
    if status == "verified" and not getattr(rule, "is_demo_only", True):
        return "SOURCE_VERIFIED"
    return "DEMO_ONLY"
