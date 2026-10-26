"""Page-level PDF text extraction (PyMuPDF) with optional Tesseract OCR fallback.

Heuristic: a page whose text layer has fewer than ``min_page_text_chars`` non-whitespace characters is
"insufficient" and becomes an OCR candidate. If OCR is unavailable, disabled or fails, the page is kept
with an explicit status; it is never reported as a successful empty extraction.

Resource bounds: at most ``max_processing_pages`` pages; OCR renders at ``ocr_dpi`` capped to
``MAX_OCR_PIXELS``; each Tesseract call has a timeout. Failure reasons are fixed, client-safe strings.
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pymupdf

from app.models.enums import PageExtractionMethod, PageStatus, ProcessingStatus

logger = logging.getLogger("regulens.pdf_text")

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_OCR_PIXELS = 20_000_000
DEFAULT_WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
_WS = re.compile(r"\s+")


IMAGE_SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpeg"))


def as_pdf_bytes(raw: bytes) -> bytes:
    """PDF bytes for a stored document. Standalone images are wrapped in a one-page PDF *in memory* (the stored
    original is never modified); PDFs are returned unchanged."""
    for signature, filetype in IMAGE_SIGNATURES:
        if raw.startswith(signature):
            with pymupdf.open(stream=raw, filetype=filetype) as img:
                return img.convert_to_pdf()
    return raw


def non_ws_len(text: str) -> int:
    return len(_WS.sub("", text))


class OcrError(Exception):
    """OCR failed. The message is client-safe."""


class OcrEngine(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def recognize(self, png: bytes) -> str: ...


class TesseractOcr:
    name = "tesseract"

    def __init__(self, command: str | None, language: str = "eng", timeout: int = 30) -> None:
        self.command = command
        self.language = language
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings) -> "TesseractOcr":
        return cls(resolve_tesseract(settings.tesseract_cmd) if settings.ocr_enabled else None,
                   settings.ocr_language, settings.ocr_timeout_seconds)

    @property
    def available(self) -> bool:
        return self.command is not None

    def recognize(self, png: bytes) -> str:
        if self.command is None:
            raise OcrError("OCR is not available.")
        try:
            result = subprocess.run(
                [self.command, "stdin", "stdout", "-l", self.language, "--psm", "3"],
                input=png, capture_output=True, timeout=self.timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError("OCR timed out for this page.") from exc
        except OSError as exc:
            raise OcrError("The OCR engine could not be started.") from exc
        if result.returncode != 0:
            raise OcrError("The OCR engine reported an error for this page.")
        return result.stdout.decode("utf-8", errors="replace")


def resolve_tesseract(configured: str) -> str | None:
    """Return a usable Tesseract executable or None. Never raises."""
    candidates = [configured] if configured else ["tesseract", str(DEFAULT_WINDOWS_TESSERACT)]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return None


@dataclass
class PageResult:
    page_number: int  # 1-based
    method: PageExtractionMethod
    status: PageStatus
    text: str
    warnings: list[str] = field(default_factory=list)
    # Evidence coordinates: lines with normalised boxes [x0, y0, x1, y1] (origin top-left of the displayed page).
    # Text-layer lines carry confidence None; OCR lines carry the engine's recognition score.
    lines: list[dict] = field(default_factory=list)
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    rotation_degrees: int = 0


@dataclass
class TextExtractionResult:
    status: ProcessingStatus
    page_count: int = 0
    pages: list[PageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failure_code: str | None = None
    failure_reason: str | None = None
    ocr_available: bool = False
    pdf_properties: dict = field(default_factory=dict)


def _failed(code: str, reason: str, ocr_available: bool, **extra) -> TextExtractionResult:
    return TextExtractionResult(status=ProcessingStatus.FAILED, failure_code=code, failure_reason=reason,
                                ocr_available=ocr_available, **extra)


def _pdf_properties(raw: bytes, doc: "pymupdf.Document") -> dict:
    meta = doc.metadata or {}
    return {
        # Each incremental save appends another %%EOF. Common for edited or signed PDFs; not evidence of tampering.
        "eof_markers": raw.count(b"%%EOF"),
        "title": (meta.get("title") or "")[:200],
        "producer": (meta.get("producer") or "")[:200],
        "creator": (meta.get("creator") or "")[:200],
        "repaired": bool(getattr(doc, "is_repaired", False)),
    }


def _render_png(page: "pymupdf.Page", dpi: int, rotate: int = 0) -> bytes:
    zoom = dpi / 72
    width, height = page.rect.width * zoom, page.rect.height * zoom
    if width * height > MAX_OCR_PIXELS:
        zoom *= (MAX_OCR_PIXELS / (width * height)) ** 0.5
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom).prerotate(rotate)).tobytes("png")


def extract_text(path: Path, ocr: OcrEngine | None, *, min_chars: int, max_pages: int, dpi: int) -> TextExtractionResult:
    ocr_available = bool(ocr and ocr.available)
    try:
        raw = path.read_bytes()
    except OSError:
        return _failed("content_unavailable", "The stored file could not be read.", ocr_available)
    try:
        doc = pymupdf.open(stream=as_pdf_bytes(raw), filetype="pdf")
    except Exception:  # PyMuPDF raises several types for malformed input
        return _failed("unreadable_pdf", "The file could not be parsed as a PDF.", ocr_available)

    with doc:
        properties = _pdf_properties(raw, doc)
        if doc.needs_pass or doc.is_encrypted:
            return _failed("encrypted_pdf", "The PDF is password-protected; its text cannot be extracted.",
                           ocr_available, pdf_properties=properties)
        if doc.page_count == 0:
            return _failed("empty_pdf", "The PDF contains no pages.", ocr_available, pdf_properties=properties)

        result = TextExtractionResult(status=ProcessingStatus.COMPLETED, page_count=doc.page_count,
                                      ocr_available=ocr_available, pdf_properties=properties)
        if doc.page_count > max_pages:
            result.warnings.append(f"Only the first {max_pages} of {doc.page_count} pages were processed.")
        if properties["repaired"]:
            result.warnings.append("The PDF structure was damaged and had to be repaired while reading.")

        for index in range(min(doc.page_count, max_pages)):
            result.pages.append(_extract_page(doc, index, ocr, min_chars=min_chars, dpi=dpi))

    usable = [p for p in result.pages if p.status == PageStatus.OK]
    if not usable:
        if not ocr_available:
            result.status = ProcessingStatus.FAILED
            result.failure_code = "ocr_unavailable"
            result.failure_reason = ("No page has a usable text layer and OCR is not available. "
                                     "Enable a local OCR engine (Tesseract or RapidOCR, see README) or review the document manually.")
        else:
            result.status = ProcessingStatus.FAILED
            result.failure_code = "no_readable_text"
            result.failure_reason = "No readable text could be extracted from any page, including by OCR."
    elif len(usable) < len(result.pages) or result.warnings:
        result.status = ProcessingStatus.COMPLETED_WITH_WARNINGS
    for page in result.pages:
        result.warnings.extend(f"Page {page.page_number}: {w}" for w in page.warnings)
    return result


def _extract_page(doc, index: int, ocr: OcrEngine | None, *, min_chars: int, dpi: int) -> PageResult:
    number = index + 1
    try:
        page = doc.load_page(index)
        text = page.get_text("text") or ""
    except Exception:
        return PageResult(number, PageExtractionMethod.NONE, PageStatus.INSUFFICIENT_TEXT, "",
                          ["The page could not be read."])

    if non_ws_len(text) >= min_chars:
        return PageResult(number, PageExtractionMethod.TEXT_LAYER, PageStatus.OK, text, lines=_text_layer_lines(page))

    method = PageExtractionMethod.TEXT_LAYER if text.strip() else PageExtractionMethod.NONE
    if ocr is None or not ocr.available:
        return PageResult(number, method, PageStatus.INSUFFICIENT_TEXT, text,
                          ["Too little text in the text layer, and OCR is not available."])
    engine_name = getattr(ocr, "name", "ocr")
    try:
        if hasattr(ocr, "recognize_detailed"):
            detailed = _ocr_with_rotation(ocr, page, dpi, min_chars)
            ocr_text, lines = detailed.text, [ln.as_dict() for ln in detailed.lines]
            conf, rotation, extra = detailed.mean_confidence, detailed.rotation_degrees, detailed.warnings
        else:
            ocr_text, lines, conf, rotation, extra = ocr.recognize(_render_png(page, dpi)), [], None, 0, []
    except OcrError as exc:
        return PageResult(number, method, PageStatus.OCR_FAILED, text, [str(exc)], ocr_engine=engine_name)
    except Exception:
        logger.warning("Unexpected OCR failure", extra={"error_type": "ocr"})
        return PageResult(number, method, PageStatus.OCR_FAILED, text, ["OCR failed for this page."],
                          ocr_engine=engine_name)
    warnings = ["Text obtained by OCR; recognition errors are possible.", *extra]
    if conf is not None and conf < LOW_OCR_CONFIDENCE:
        warnings.append(f"Low OCR confidence on this page (mean {conf:.2f}); values may be misread.")
    common = dict(lines=lines, ocr_engine=engine_name, ocr_confidence=conf, rotation_degrees=rotation)
    if non_ws_len(ocr_text) >= min_chars:
        return PageResult(number, PageExtractionMethod.OCR, PageStatus.OK, ocr_text, warnings, **common)
    return PageResult(number, PageExtractionMethod.OCR, PageStatus.OCR_LOW_TEXT, ocr_text,
                      [*warnings, "OCR produced too little text to rely on (blank, unreadable or very low-resolution page)."],
                      **common)


LOW_OCR_CONFIDENCE = 0.80
ROTATION_RETRY_CONFIDENCE = 0.6


def _ocr_with_rotation(ocr, page, dpi: int, min_chars: int):
    """OCR the page upright; only if the result is weak, try 90/180/270° and keep the clearly better reading.
    No other preprocessing is applied, so stamps, signatures and identifiers are not altered."""
    best = ocr.recognize_detailed(_render_png(page, dpi))
    weak = non_ws_len(best.text) < min_chars or (best.mean_confidence or 0) < ROTATION_RETRY_CONFIDENCE
    if not weak:
        return best
    for degrees in (90, 180, 270):
        candidate = ocr.recognize_detailed(_render_png(page, dpi, rotate=degrees))
        if candidate.score > best.score * 1.5 and non_ws_len(candidate.text) >= min_chars:
            candidate.rotation_degrees = degrees
            candidate.warnings.append(f"Page appeared rotated; OCR used the page turned {degrees}° clockwise.")
            best = candidate
    return best


def _text_layer_lines(page) -> list[dict]:
    """Text-layer lines with normalised boxes (displayed orientation)."""
    try:
        data = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return []
    w, h = page.rect.width or 1, page.rect.height or 1
    out = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            out.append({"text": text, "confidence": None,
                        "box": [round(max(x0, 0) / w, 4), round(max(y0, 0) / h, 4), round(min(x1, w) / w, 4),
                                round(min(y1, h) / h, 4)]})
            if len(out) >= 400:
                return out
    return out
