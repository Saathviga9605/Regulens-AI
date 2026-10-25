import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[2] / "rules-registry" / "scripts" / "verify_candidate.py"
SPEC = importlib.util.spec_from_file_location("verify_candidate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
verify_candidate_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_candidate_module)


def make_files(tmp_path: Path) -> tuple[Path, Path]:
    quote = "An exact synthetic clause quote."
    page_record = {
        "source_sha256": "a" * 64,
        "pdf_page_number": 2,
        "printed_page_label": None,
        "text": f"Heading\\n{quote}\\nFooter\\n",
        "text_sha256": "b" * 64,
        "char_count": len(f"Heading\\n{quote}\\nFooter\\n"),
        "extraction_method": "text_layer",
        "ocr_derived": False,
    }
    pages = tmp_path / "pages.jsonl"
    pages.write_text(json.dumps(page_record) + "\n", encoding="utf-8")
    start = page_record["text"].index(quote)
    candidate = {
        "schema_version": 1,
        "rule_id": "APH-101",
        "slug": "synthetic-clause",
        "status": "draft",
        "provenance": "regulatory",
        "citation": {
            "source_sha256": page_record["source_sha256"],
            "pdf_page_number": 2,
            "printed_page_label": "1",
            "clause_reference": "Section 1.1",
            "quote": quote,
            "quote_start_offset": start,
            "quote_end_offset": start + len(quote),
            "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            "ocr_derived": False,
        },
        "applicability_status": "unresolved",
        "proposed_rule": {"rule_type": "expected_document", "parameters": {"category": "example"}},
        "blocking_gaps": ["Synthetic fixture: application applicability has not been reviewed."],
    }
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    return candidate_path, pages


def test_verifies_exact_quote_and_hashes(tmp_path: Path) -> None:
    candidate, pages = make_files(tmp_path)
    assert verify_candidate_module.verify_candidate(candidate, pages) == []


def test_rejects_tampered_quote_offset(tmp_path: Path) -> None:
    candidate_path, pages = make_files(tmp_path)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["citation"]["quote_start_offset"] += 1
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    errors = verify_candidate_module.verify_candidate(candidate_path, pages)
    assert "quote does not match the exact extracted text at its recorded offsets" in errors


def test_candidate_cannot_be_marked_approved(tmp_path: Path) -> None:
    candidate_path, pages = make_files(tmp_path)
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["status"] = "approved"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    errors = verify_candidate_module.verify_candidate(candidate_path, pages)
    assert any("Input should be 'draft'" in error for error in errors)
