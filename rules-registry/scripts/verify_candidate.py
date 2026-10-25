"""Verify a local draft candidate's source hash, exact quote span, and non-approved status."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(StrictModel):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_page_number: int = Field(ge=1)
    printed_page_label: str | None
    clause_reference: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    quote_start_offset: int = Field(ge=0)
    quote_end_offset: int = Field(ge=1)
    quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ocr_derived: bool


class Candidate(StrictModel):
    schema_version: Literal[1]
    rule_id: str = Field(pattern=r"^[A-Z]{2,6}-\d{3}$")
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: Literal["draft"]
    provenance: Literal["regulatory"]
    citation: Citation
    applicability_status: Literal["unresolved", "resolved"]
    proposed_rule: dict
    blocking_gaps: list[str]


def verify_candidate(candidate_path: Path, pages_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        candidate = Candidate.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        return [f"candidate schema/read error: {exc}"]

    records: dict[int, dict] = {}
    try:
        with pages_path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"page record {line_number} is invalid JSON: {exc.msg}")
                    continue
                page_number = record.get("pdf_page_number")
                if not isinstance(page_number, int) or page_number in records:
                    errors.append(f"page record {line_number} has an invalid or duplicate page number")
                    continue
                records[page_number] = record
    except OSError as exc:
        return [f"page extraction read error: {exc}"]

    citation = candidate.citation
    page = records.get(citation.pdf_page_number)
    if page is None:
        return [*errors, f"cited PDF page {citation.pdf_page_number} is not present"]
    if page.get("source_sha256") != citation.source_sha256:
        errors.append("candidate source SHA-256 does not match the extracted source")
    if page.get("ocr_derived") is not citation.ocr_derived:
        errors.append("candidate OCR flag does not match the extracted page")

    text = page.get("text")
    if not isinstance(text, str):
        return [*errors, "extracted page text is not a string"]
    start, end = citation.quote_start_offset, citation.quote_end_offset
    if end <= start or end > len(text) or text[start:end] != citation.quote:
        errors.append("quote does not match the exact extracted text at its recorded offsets")
    if hashlib.sha256(citation.quote.encode("utf-8")).hexdigest() != citation.quote_sha256:
        errors.append("quote SHA-256 does not match the candidate quote")
    if candidate.applicability_status == "unresolved" and not candidate.blocking_gaps:
        errors.append("unresolved applicability must have at least one blocking gap")
    if candidate.applicability_status == "resolved" and candidate.blocking_gaps:
        errors.append("resolved applicability cannot retain blocking gaps")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="Local draft candidate JSON")
    parser.add_argument(
        "--pages",
        type=Path,
        default=Path("rules-registry/source/local/pages.jsonl"),
        help="Local extracted pages JSONL",
    )
    args = parser.parse_args()

    errors = verify_candidate(args.candidate, args.pages)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: candidate schema and exact source quote verified; candidate remains a draft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
