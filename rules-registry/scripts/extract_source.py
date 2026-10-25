"""Extract local PDF text with page provenance; this does not approve or validate rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pymupdf


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def extract(input_path: Path, output_path: Path, *, overwrite: bool = False) -> tuple[int, int, int]:
    source = input_path.resolve(strict=True)
    output = output_path.resolve()
    if not source.is_file():
        raise ValueError(f"Source is not a regular file: {source}")
    if source.suffix.casefold() != ".pdf":
        raise ValueError("Source must be a PDF.")
    if source == output:
        raise ValueError("Output path must not overwrite the source PDF.")
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists; pass --overwrite to replace it: {output}")

    source_digest = sha256_bytes(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output.with_name(f".{output.name}.tmp")
    total_chars = 0
    empty_pages = 0
    page_count = 0
    try:
        with pymupdf.open(source) as document, temp_path.open("w", encoding="utf-8", newline="\n") as stream:
            if document.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported by this extractor.")
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text", sort=False)
                page_count += 1
                char_count = len(text)
                total_chars += char_count
                if not text.strip():
                    empty_pages += 1
                record = {
                    "source_sha256": source_digest,
                    "pdf_page_number": page_index,
                    "printed_page_label": None,
                    "text": text,
                    "text_sha256": sha256_bytes(text.encode("utf-8")),
                    "char_count": char_count,
                    "extraction_method": "text_layer" if text.strip() else "none",
                    "ocr_derived": False,
                }
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        temp_path.replace(output)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return page_count, total_chars, empty_pages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local PDF source file")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("rules-registry/source/local/pages.jsonl"),
        help="Ignored local output path (default: rules-registry/source/local/pages.jsonl)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing extraction output")
    args = parser.parse_args()

    try:
        pages, chars, empty = extract(args.source, args.output, overwrite=args.overwrite)
    except (OSError, ValueError, pymupdf.FileDataError) as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    print(f"Extracted pages: {pages}; characters: {chars}; pages with no text layer: {empty}")
    print(f"Local output: {args.output.resolve()}")
    if empty:
        print("Warning: empty text-layer pages need separate visual/OCR review; no OCR was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
