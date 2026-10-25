"""Local OCR providers with line-level confidence and coordinates.

Providers (all local; nothing is ever sent to a remote service):

* ``tesseract`` — the Tesseract executable (``REGULENS_TESSERACT_CMD``), word-level TSV output grouped into lines.
* ``rapidocr`` — RapidOCR (PP-OCR detection + recognition networks run with ONNX Runtime on the CPU; the model
  files ship inside the ``rapidocr-onnxruntime`` wheel, nothing is downloaded at run time).
* ``none`` — OCR disabled.

``REGULENS_OCR_ENGINE=auto`` picks Tesseract if its executable is found, otherwise RapidOCR if importable,
otherwise none. The choice is explicit and reported by ``/system/info``.

Coordinate convention: boxes are ``[x0, y0, x1, y1]`` normalised to 0–1 of the rendered page, origin top-left,
in the page's *displayed* orientation (after any rotation applied for OCR, which is recorded separately).
Confidence values are the engine's own recognition scores (0–1). They are not calibrated probabilities that a
value is correct.
"""

from __future__ import annotations

import csv
import io
import logging
import subprocess
import threading
from dataclasses import dataclass, field

import numpy as np

from app.services.pdf_text import OcrError, TesseractOcr, resolve_tesseract

logger = logging.getLogger("regulens.ocr")


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: list[float]  # [x0, y0, x1, y1] normalised, origin top-left

    def as_dict(self) -> dict:
        return {"text": self.text, "confidence": round(self.confidence, 4), "box": [round(v, 4) for v in self.box]}


@dataclass
class OcrPage:
    text: str
    lines: list[OcrLine]
    engine: str
    engine_version: str
    rotation_degrees: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def mean_confidence(self) -> float | None:
        weighted = [(ln.confidence, len(ln.text)) for ln in self.lines if ln.text.strip()]
        total = sum(n for _, n in weighted)
        return round(sum(c * n for c, n in weighted) / total, 4) if total else None

    @property
    def score(self) -> float:
        return sum(ln.confidence * len(ln.text.strip()) for ln in self.lines)


def _decode(png: bytes) -> np.ndarray:
    import cv2

    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise OcrError("The page image could not be decoded for OCR.")
    return img


def _lines_text(lines: list[OcrLine]) -> str:
    return "\n".join(ln.text for ln in lines)


class TesseractDetailed(TesseractOcr):
    """Tesseract with TSV output (word confidences and boxes grouped into lines)."""

    def engine_version(self) -> str:
        if self.command is None:
            return "unavailable"
        try:
            out = subprocess.run([self.command, "--version"], capture_output=True, timeout=10, check=False)
            first = (out.stdout or out.stderr).decode("utf-8", "replace").splitlines()
            return first[0].strip() if first else "tesseract"
        except (OSError, subprocess.TimeoutExpired):
            return "tesseract"

    def recognize_detailed(self, png: bytes) -> OcrPage:
        if self.command is None:
            raise OcrError("OCR is not available.")
        img = _decode(png)
        h, w = img.shape[:2]
        try:
            result = subprocess.run([self.command, "stdin", "stdout", "-l", self.language, "--psm", "3", "tsv"],
                                    input=png, capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise OcrError("OCR timed out for this page.") from exc
        except OSError as exc:
            raise OcrError("The OCR engine could not be started.") from exc
        if result.returncode != 0:
            raise OcrError("The OCR engine reported an error for this page.")
        lines = parse_tesseract_tsv(result.stdout.decode("utf-8", errors="replace"), w, h)
        return OcrPage(_lines_text(lines), lines, "tesseract", self.engine_version())


def parse_tesseract_tsv(tsv: str, width: int, height: int) -> list[OcrLine]:
    """Group Tesseract TSV words (level 5) into lines; confidence = mean word confidence / 100."""
    groups: dict[tuple, list[dict]] = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        try:
            conf = float(row["conf"])
        except (TypeError, ValueError):
            continue
        if conf < 0:
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        groups.setdefault(key, []).append({**row, "conf": conf})
    lines = []
    for words in groups.values():
        xs0 = [int(wd["left"]) for wd in words]
        ys0 = [int(wd["top"]) for wd in words]
        xs1 = [int(wd["left"]) + int(wd["width"]) for wd in words]
        ys1 = [int(wd["top"]) + int(wd["height"]) for wd in words]
        lines.append(OcrLine(" ".join(wd["text"] for wd in words), sum(wd["conf"] for wd in words) / len(words) / 100,
                             [min(xs0) / width, min(ys0) / height, max(xs1) / width, max(ys1) / height]))
    lines.sort(key=lambda ln: (round(ln.box[1], 2), ln.box[0]))
    return lines


class RapidOcrEngine:
    """PP-OCR (ONNX Runtime, CPU). Initialised lazily; calls are serialised to bound CPU and memory."""

    name = "rapidocr"

    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.Lock()
        self._version = None
        self._error: str | None = None
        try:
            import importlib.metadata as md

            self._version = f"rapidocr-onnxruntime {md.version('rapidocr-onnxruntime')}, onnxruntime {md.version('onnxruntime')}"
        except Exception:  # noqa: BLE001 - not installed
            self._error = "rapidocr-onnxruntime is not installed"

    @property
    def available(self) -> bool:
        return self._error is None

    def engine_version(self) -> str:
        return self._version or "unavailable"

    def _get(self):
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()
            except Exception as exc:  # noqa: BLE001
                self._error = f"RapidOCR could not start ({type(exc).__name__})"
                raise OcrError("The OCR engine could not be started.") from exc
        return self._engine

    def recognize(self, png: bytes) -> str:
        return self.recognize_detailed(png).text

    def recognize_detailed(self, png: bytes) -> OcrPage:
        img = _decode(png)
        h, w = img.shape[:2]
        with self._lock:
            try:
                result, _ = self._get()(img)
            except OcrError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise OcrError("The OCR engine reported an error for this page.") from exc
        lines = []
        for quad, text, conf in result or []:
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            lines.append(OcrLine(str(text), float(conf), [min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h]))
        lines.sort(key=lambda ln: (round(ln.box[1], 2), ln.box[0]))
        return OcrPage(_lines_text(lines), lines, "rapidocr", self.engine_version())


class NoOcr:
    name = "none"
    available = False

    def engine_version(self) -> str:
        return "unavailable"

    def recognize(self, png: bytes) -> str:  # pragma: no cover - never called when unavailable
        raise OcrError("OCR is not available.")


def build_ocr_engine(settings):
    """Explicit, local-only provider selection. Never returns a remote client."""
    if not settings.ocr_enabled or settings.ocr_engine == "none":
        return NoOcr()
    if settings.ocr_engine in ("auto", "tesseract"):
        tess = TesseractDetailed(resolve_tesseract(settings.tesseract_cmd), settings.ocr_language,
                                 settings.ocr_timeout_seconds)
        if tess.available or settings.ocr_engine == "tesseract":
            return tess
    rapid = RapidOcrEngine()
    if rapid.available or settings.ocr_engine == "rapidocr":
        return rapid
    return NoOcr()


def describe(engine) -> dict:
    return {"engine": getattr(engine, "name", "none"), "available": bool(getattr(engine, "available", False)),
            "version": engine.engine_version() if hasattr(engine, "engine_version") else "unknown",
            "local_only": True}
