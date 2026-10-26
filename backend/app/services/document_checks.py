"""Document integrity *indicators* (not authentication).

* **QR payloads** — QR codes on each page are decoded locally with OpenCV. A payload is untrusted text: it is only
  compared with the extracted certificate number (``consistent`` / ``inconsistent`` / ``no_reference``). A decoded or
  consistent QR code does not establish authenticity — anyone can print a QR code.
* **Reference format** — a generic plausibility check of the extracted certificate number (characters, length, contains
  digits). It is not an issuer-specific format and does not establish that the number exists.
* **PDF signatures** — whether the PDF contains signature fields. Cryptographic validation needs a validation library
  and configured trust roots, which are not available, so signatures are reported as present but **not validated**
  (source type ``NOT_CONNECTED``).
"""

from __future__ import annotations

import re

import numpy as np
import pymupdf

from app.services.normalize import normalize_identifier
from app.services.pdf_text import as_pdf_bytes

CHECKS_VERSION = "integrity_indicators_v1"
MAX_PAGES = 10
QR_DPI = 200
_REF = re.compile(r"^[A-Za-z0-9/.\-_ ]{4,40}$")


def qr_payloads(pdf: bytes) -> list[dict]:
    import cv2

    detector = cv2.QRCodeDetector()
    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        for index in range(min(doc.page_count, MAX_PAGES)):
            pix = doc[index].get_pixmap(dpi=QR_DPI, colorspace=pymupdf.csGRAY, alpha=False)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
            try:
                ok, values, _points, _ = detector.detectAndDecodeMulti(img)
            except cv2.error:
                ok, values = False, ()
            for value in (values if ok else ()):
                if value:
                    out.append({"page": index + 1, "payload": value[:500]})
    return out


def reference_format(certificate_number: str | None) -> dict:
    if not certificate_number:
        return {"status": "not_available", "detail": "No certificate number was extracted with grounded evidence."}
    value = certificate_number.strip()
    problems = []
    if not _REF.fullmatch(value):
        problems.append("unexpected characters or length (allowed: letters, digits, / . - _ space; 4–40 characters)")
    if not re.search(r"\d", value):
        problems.append("contains no digits")
    return {"status": "plausible" if not problems else "implausible", "value": value, "problems": problems,
            "note": "Generic plausibility only; not an issuer-specific format and not proof the number exists."}


def signature_info(pdf: bytes) -> dict:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        flags = doc.get_sigflags() if hasattr(doc, "get_sigflags") else -1
        count = 0
        for page in doc:
            for widget in page.widgets() or []:
                if widget.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                    count += 1
    return {"signature_fields": count, "signed_flag": flags > 0, "validated": False, "source_type": "NOT_CONNECTED",
            "detail": "Cryptographic signature validation is not supported in this installation (no validation library "
                      "or trust roots configured); signature fields are reported, not verified."}


def run_checks(raw: bytes, certificate_number: str | None, certificate_quote_page: int | None) -> dict:
    pdf = as_pdf_bytes(raw)
    payloads = qr_payloads(pdf)
    target = normalize_identifier(certificate_number) if certificate_number else None
    for p in payloads:
        if target is None:
            p["comparison"] = "no_reference"
        else:
            p["comparison"] = "consistent" if target in normalize_identifier(p["payload"]) else "inconsistent"
    return {
        "version": CHECKS_VERSION,
        "qr": {"codes": payloads, "found": len(payloads),
               "note": "QR contents are untrusted text compared with the extracted certificate number; a QR code does "
                       "not establish authenticity."},
        "reference_format": reference_format(certificate_number),
        "certificate_number_page": certificate_quote_page,
        "pdf_signature": signature_info(pdf),
        "disclaimer": "Integrity indicators for human review. None of these establishes that a document is genuine.",
    }
