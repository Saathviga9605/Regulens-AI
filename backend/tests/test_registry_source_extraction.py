import json
import importlib.util
from pathlib import Path

import pymupdf
import pytest

SCRIPT_PATH = Path(__file__).parents[2] / "rules-registry" / "scripts" / "extract_source.py"
SPEC = importlib.util.spec_from_file_location("extract_source", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extract_source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract_source)
extract = extract_source.extract


@pytest.fixture
def pdf_source(tmp_path: Path) -> Path:
    path = tmp_path / "source.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Clause 4.2 - Synthetic fixture text.")
        document.new_page()
        document.save(path)
    return path


def test_extracts_page_text_hashes_and_empty_page_metadata(tmp_path: Path, pdf_source: Path) -> None:
    output = tmp_path / "local" / "pages.jsonl"
    page_count, total_chars, empty_pages = extract(pdf_source, output)
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

    assert (page_count, empty_pages) == (2, 1)
    assert total_chars == len(records[0]["text"]) + len(records[1]["text"])
    assert [record["pdf_page_number"] for record in records] == [1, 2]
    assert records[0]["text"] == "Clause 4.2 - Synthetic fixture text.\n"
    assert records[0]["printed_page_label"] is None
    assert records[0]["extraction_method"] == "text_layer"
    assert records[1]["extraction_method"] == "none"
    assert all(record["ocr_derived"] is False for record in records)
    assert records[0]["source_sha256"] == records[1]["source_sha256"]
    assert records[0]["text_sha256"] != records[1]["text_sha256"]


def test_does_not_overwrite_existing_output_without_explicit_flag(tmp_path: Path, pdf_source: Path) -> None:
    output = tmp_path / "pages.jsonl"
    output.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        extract(pdf_source, output)

    assert output.read_text(encoding="utf-8") == "keep me"


def test_rejects_source_output_collision(pdf_source: Path) -> None:
    with pytest.raises(ValueError, match="must not overwrite"):
        extract(pdf_source, pdf_source)
