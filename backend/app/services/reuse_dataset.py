"""Synthetic, deterministic evaluation dataset for cross-case reuse detection (``reuse_ds_v1``).

Every document is fictional and carries the demo banner. Pairs are labelled at pair level:

* ``reuse`` — the same underlying source document, possibly transformed (positive).
* ``altered`` — derived from the same source with one critical field changed. Reported separately: the
  expected engine behaviour is ``CANDIDATE`` (possible alteration for review), and these pairs are excluded from
  the binary precision/recall counts so neither "positive" nor "negative" is assumed for them.
* ``distinct`` — different underlying documents (negative); ``hard_negative`` marks same-template, same-issuer,
  similar-logo and same-institution negatives.

The ``dev`` split is used to choose thresholds; the ``heldout`` split uses different fictional issuers,
institutions and documents and is evaluated only with frozen thresholds. Sources and transformations are
generated from fixed seeds, so the dataset is byte-reproducible for a given PyMuPDF/OpenCV version.

v2 adds a ``dev2`` split (simulated printed-and-photographed copies, poor scans, OCR cases) and a fresh
``heldout2`` split with new fictional issuers and documents, evaluated only after all v3 changes were frozen. The
v1 pairs and their bytes are unchanged. "Photographed" copies are *simulated* (perspective warp onto a background,
lighting gradient, sensor noise, blur, JPEG); no real phone photographs were taken. Campus-photo pairs are not
included.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pymupdf

from app.services.demo_documents import BANNER
from app.services.reuse_visual import cv2

DATASET_VERSION = "reuse_ds_v2"  # v2 = v1 pairs unchanged + dev2 and heldout2 splits


@dataclass
class FixtureDoc:
    key: str
    case: str  # fictional application case
    category: str
    pdf: bytes
    recipe: str  # how it was produced (source → transformation)
    source_key: str | None = None
    expected_fields: dict = field(default_factory=dict)  # institution_name / certificate_number / issue_date (ISO)
    has_text_layer: bool = True


@dataclass
class FixturePair:
    key: str
    a: str
    b: str
    label: str  # reuse / altered / distinct
    split: str  # dev / heldout
    hard_negative: bool
    scenario: str
    hero: bool = False
    transform: str = "none"  # transformation type of the copy (for per-type reporting)
    quality: str = "clean"  # clean / degraded / poor


@dataclass
class Dataset:
    version: str
    docs: dict[str, FixtureDoc]
    pairs: list[FixturePair]

    def composition(self) -> dict:
        out: dict = {"documents": len(self.docs), "cases": len({d.case for d in self.docs.values()}), "pairs": {}}
        for split in sorted({p.split for p in self.pairs}):
            ps = [p for p in self.pairs if p.split == split]
            out["pairs"][split] = {"total": len(ps), "reuse": sum(p.label == "reuse" for p in ps),
                                   "altered": sum(p.label == "altered" for p in ps),
                                   "distinct": sum(p.label == "distinct" for p in ps),
                                   "hard_negative": sum(p.hard_negative for p in ps)}
        return out


# --- source documents ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Layout:
    issuer: str
    title: str
    logo: str  # initials drawn in the seal
    accent: tuple[float, float, float]
    border: bool = True
    body: tuple[str, ...] = ()


def _draw_frame(page: pymupdf.Page, layout: Layout) -> None:
    if layout.border:
        page.draw_rect(pymupdf.Rect(24, 24, 571, 818), color=layout.accent, width=2.2)
        page.draw_rect(pymupdf.Rect(30, 30, 565, 812), color=layout.accent, width=0.6)
    page.draw_circle((520, 110), 34, color=layout.accent, width=2.0)
    page.draw_circle((520, 110), 27, color=layout.accent, width=0.8)
    page.insert_text((503, 116), layout.logo, fontsize=16, color=layout.accent)
    page.insert_text((44, 52), BANNER, fontsize=7.5, color=(0.75, 0, 0))
    page.insert_text((44, 800), BANNER, fontsize=7.5, color=(0.75, 0, 0))


def certificate(layout: Layout, *, number: str, institution: str, address: str, issue: str, valid: str | None,
                extra: tuple[str, ...] = (), seal_text: str = "") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _draw_frame(page, layout)
    page.insert_text((60, 100), layout.issuer, fontsize=11, color=layout.accent)
    page.insert_text((60, 150), layout.title, fontsize=17)
    lines = [f"Certificate No.: {number}", f"Name of Institution: {institution}", f"Address: {address}",
             f"Date of Issue: {issue}"]
    if valid:
        lines.append(f"Valid Until: {valid}")
    lines += ["", *layout.body, *extra, "", "This is a fictional document generated for software evaluation only."]
    y = 200
    for line in lines:
        page.insert_text((60, y), line, fontsize=11)
        y += 21
    page.draw_line((360, 720), (530, 720), color=(0.2, 0.2, 0.2), width=0.8)
    page.insert_text((372, 738), seal_text or "Authorised signatory (fictional)", fontsize=9)
    doc.set_metadata({"title": f"Fictional evaluation document: {layout.title}", "producer": "ReguLens AI reuse_ds_v1"})
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def letter(layout: Layout, *, heading: str, paragraphs: tuple[str, ...]) -> bytes:
    """Unrelated body content on the same frame/logo (similar-logo hard negatives)."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _draw_frame(page, layout)
    page.insert_text((60, 100), layout.issuer, fontsize=11, color=layout.accent)
    page.insert_text((60, 160), heading, fontsize=15)
    y = 210
    for para in paragraphs:
        page.insert_text((60, y), para, fontsize=10.5)
        y += 19
    doc.set_metadata({"title": f"Fictional evaluation letter: {heading}", "producer": "ReguLens AI reuse_ds_v1"})
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def blank_scan(seed: int) -> bytes:
    """An image-only page with almost no content (unreadable/missing evidence case)."""
    rng = np.random.default_rng(seed)
    img = np.full((1170, 827), 246, np.uint8)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    return _image_pdf(img)


# --- transformations -----------------------------------------------------------------------------

def rasterize(pdf: bytes, dpi: int = 150) -> np.ndarray:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), colorspace=pymupdf.csGRAY, alpha=False)
        return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()


def _image_pdf(img: np.ndarray, jpeg_quality: int | None = None) -> bytes:
    if jpeg_quality:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    else:
        ok, buf = cv2.imencode(".png", img)
    assert ok
    h, w = img.shape[:2]
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=595 * h / w)
    page.insert_image(page.rect, stream=buf.tobytes())
    doc.set_metadata({"title": "Fictional evaluation scan", "producer": "ReguLens AI reuse_ds_v1 (raster)"})
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def t_metadata(pdf: bytes) -> bytes:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    doc.set_metadata({"title": "Re-saved copy", "producer": "Another PDF tool (fictional)", "author": "unknown"})
    return doc.tobytes(garbage=4, deflate=True, clean=True, no_new_id=True)


def t_vector_rotate_scale(pdf: bytes, rotate: int, scale: float) -> bytes:
    """Place the original page scaled on a new page and rotate it (text layer preserved)."""
    src = pymupdf.open(stream=pdf, filetype="pdf")
    out = pymupdf.open()
    page = out.new_page(width=595, height=842)
    w, h = 595 * scale, 842 * scale
    rect = pymupdf.Rect((595 - w) / 2, (842 - h) / 2, (595 + w) / 2, (842 + h) / 2)
    page.show_pdf_page(rect, src, 0)
    if rotate:
        page.set_rotation(rotate)
    out.set_metadata({"title": "Rescaled copy", "producer": "ReguLens AI reuse_ds_v1"})
    return out.tobytes(garbage=3, deflate=True, no_new_id=True)


def t_vector_crop(pdf: bytes, margin: float) -> bytes:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    r = doc[0].rect
    doc[0].set_cropbox(pymupdf.Rect(r.width * margin, r.height * margin, r.width * (1 - margin), r.height * (1 - margin)))
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def t_raster(pdf: bytes, *, seed: int, rotate_deg: float = 0.0, quarter_turns: int = 0, scale: float = 1.0,
             crop: float = 0.0, brightness: float = 0.0, contrast: float = 1.0, noise: float = 0.0,
             blur: int = 0, jpeg: int | None = None, dpi: int = 150) -> bytes:
    """Scan-like raster copy (image-only PDF: no text layer)."""
    rng = np.random.default_rng(seed)
    img = rasterize(pdf, dpi).astype(np.float32)
    h, w = img.shape
    if crop:
        img = img[int(h * crop):int(h * (1 - crop)), int(w * crop):int(w * (1 - crop))]
        h, w = img.shape
    if rotate_deg:
        m = cv2.getRotationMatrix2D((w / 2, h / 2), rotate_deg, 1.0)
        img = cv2.warpAffine(img, m, (w, h), borderValue=255)
    if scale != 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    img = img * contrast + brightness + (contrast - 1) * -128
    if noise:
        img = img + rng.normal(0, noise, img.shape)
    if blur:
        img = cv2.GaussianBlur(img, (blur, blur), 0)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if quarter_turns:
        img = np.ascontiguousarray(np.rot90(img, k=-quarter_turns))
    return _image_pdf(img, jpeg)


def t_photo(pdf: bytes, *, seed: int, tilt: float = 0.06, shade: float = 0.25, noise: float = 6.0, blur: int = 3,
            jpeg: int = 70, dpi: int = 150) -> bytes:
    """Simulated printed-and-photographed copy: perspective warp onto a darker background, a lighting gradient,
    sensor noise, slight blur and JPEG compression. Image-only (no text layer)."""
    rng = np.random.default_rng(seed)
    page = rasterize(pdf, dpi).astype(np.float32)
    h, w = page.shape
    pad = int(0.08 * w)
    canvas_w, canvas_h = w + 2 * pad, h + 2 * pad
    jitter = lambda: rng.uniform(-tilt, tilt) * w  # noqa: E731
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[pad + jitter(), pad + jitter()], [pad + w + jitter(), pad + jitter()],
                      [pad + w + jitter(), pad + h + jitter()], [pad + jitter(), pad + h + jitter()]])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(page, m, (canvas_w, canvas_h), borderValue=95)
    gx = np.linspace(1 - shade, 1, canvas_w, dtype=np.float32)[None, :]
    gy = np.linspace(1, 1 - shade / 2, canvas_h, dtype=np.float32)[:, None]
    img = warped * gx * gy + rng.normal(0, noise, warped.shape)
    if blur:
        img = cv2.GaussianBlur(img, (blur, blur), 0)
    return _image_pdf(np.clip(img, 0, 255).astype(np.uint8), jpeg)


def t_poor_scan(pdf: bytes, *, seed: int) -> bytes:
    """Very low resolution, heavy blur and noise: text is not reliably readable (should not be confirmed)."""
    return t_raster(pdf, seed=seed, dpi=45, blur=7, noise=22, contrast=0.6, brightness=40, jpeg=25)


def t_change_number(layout: Layout, kwargs: dict, new_number: str) -> bytes:
    return certificate(layout, **{**kwargs, "number": new_number})


# --- dataset -------------------------------------------------------------------------------------

FIRE_DEV = Layout("Synthetic Vindhya Fire Services (Fictional)", "FIRE SAFETY CERTIFICATE", "VF", (0.62, 0.12, 0.10),
                  body=("The fire fighting installations, exits and hydrants of the premises were inspected",
                        "and found in working order on the date of inspection (fictional)."))
OCC_DEV = Layout("Synthetic Vindhya Development Authority (Fictional)", "OCCUPANCY CERTIFICATE", "VD", (0.10, 0.25, 0.55),
                 body=("The building described above is fit for occupation for educational use (fictional).",))
LETTER_DEV = Layout("Synthetic Vindhya Fire Services (Fictional)", "", "VF", (0.62, 0.12, 0.10))

STRUCT_HO = Layout("Fictional Konkan Structural Consultants LLP", "STRUCTURAL STABILITY CERTIFICATE", "KS",
                   (0.15, 0.40, 0.30), body=("Certified structurally stable by the undersigned engineer (fictional).",
                                             "Inspection covered columns, beams, slabs and foundations."))
NOC_HO = Layout("Synthetic Narmada State University (Fictional)", "NO OBJECTION CERTIFICATE", "NU", (0.35, 0.20, 0.55),
                body=("The University has no objection to the continuation of the programmes listed",
                      "in the application, subject to the conditions of affiliation (fictional)."))
FIRE_HO = Layout("Synthetic Konkan Fire Services (Fictional)", "FIRE SAFETY CERTIFICATE", "KF", (0.70, 0.30, 0.05),
                 body=("Fire safety equipment, sprinklers and evacuation routes were inspected (fictional).",))
LETTER_HO = Layout("Synthetic Konkan Fire Services (Fictional)", "", "KF", (0.70, 0.30, 0.05))


def _fields(inst: str, number: str, iso: str) -> dict:
    return {"institution_name": inst, "certificate_number": number, "issue_date": iso}


def build_dataset() -> Dataset:
    docs: dict[str, FixtureDoc] = {}
    pairs: list[FixturePair] = []

    def add(key, case, category, pdf, recipe, source=None, fields=None, text=True):
        docs[key] = FixtureDoc(key, case, category, pdf, recipe, source, fields or {}, text)

    # ---------------- development split ----------------
    d_fire = dict(number="SYN-VFS/2026/0418", institution="Satpura Valley Institute of Technology",
                  address="12 Synthetic Ridge Road, Itarsi North 461199", issue="12 February 2026", valid="11 February 2029")
    add("dev_fire_src", "DEV-C01", "fire_safety_certificate", certificate(FIRE_DEV, **d_fire), "source",
        fields=_fields(d_fire["institution"], d_fire["number"], "2026-02-12"))
    src = docs["dev_fire_src"].pdf
    add("dev_fire_exact", "DEV-C02", "fire_safety_certificate", src, "byte copy of dev_fire_src", "dev_fire_src",
        docs["dev_fire_src"].expected_fields)
    add("dev_fire_meta", "DEV-C03", "fire_safety_certificate", t_metadata(src), "metadata changed + re-saved",
        "dev_fire_src", docs["dev_fire_src"].expected_fields)
    add("dev_fire_vec", "DEV-C04", "fire_safety_certificate", t_vector_rotate_scale(src, 90, 0.82),
        "vector copy: scaled 0.82, rotated 90°", "dev_fire_src", docs["dev_fire_src"].expected_fields)
    add("dev_fire_scan", "DEV-C05", "fire_safety_certificate",
        t_raster(src, seed=11, rotate_deg=1.2, scale=0.8, noise=6, jpeg=55),
        "raster scan: rotate 1.2°, scale 0.8, noise σ6, JPEG q55 (no text layer)", "dev_fire_src",
        docs["dev_fire_src"].expected_fields, text=False)
    add("dev_fire_crop", "DEV-C06", "fire_safety_certificate",
        t_raster(src, seed=12, crop=0.05, brightness=18, contrast=0.85, jpeg=70),
        "raster: crop 5%, brightness +18, contrast 0.85, JPEG q70 (no text layer)", "dev_fire_src",
        docs["dev_fire_src"].expected_fields, text=False)
    d_other_inst = dict(d_fire, institution="Tapti Plains College of Engineering", number="SYN-VFS/2026/0533",
                        address="4 Synthetic Canal Street, Burhanpur East 450399", issue="3 March 2026", valid="2 March 2029")
    add("dev_fire_tmpl", "DEV-C07", "fire_safety_certificate", certificate(FIRE_DEV, **d_other_inst),
        "same template, different institution/number/dates",
        fields=_fields(d_other_inst["institution"], d_other_inst["number"], "2026-03-03"))
    d_renew = dict(d_fire, number="SYN-VFS/2023/0102", issue="9 January 2023", valid="8 January 2026")
    add("dev_fire_renew", "DEV-C08", "fire_safety_certificate", certificate(FIRE_DEV, **d_renew),
        "same issuer layout and institution, earlier certificate (different number/dates)",
        fields=_fields(d_renew["institution"], d_renew["number"], "2023-01-09"))
    add("dev_fire_alter", "DEV-C09", "fire_safety_certificate", t_change_number(FIRE_DEV, d_fire, "SYN-VFS/2026/0481"),
        "dev_fire_src with certificate number changed (controlled alteration)", "dev_fire_src",
        _fields(d_fire["institution"], "SYN-VFS/2026/0481", "2026-02-12"))
    add("dev_letter", "DEV-C10", "other", letter(LETTER_DEV, heading="INSPECTION SCHEDULE NOTICE", paragraphs=(
        "Inspections in the Itarsi zone will take place between 2 and 20 November (fictional).",
        "Institutions must keep evacuation drills logged and hydrant pressure readings available.",
        "This notice is unrelated to any certificate and is generated for software evaluation only.")),
        "same frame and seal as the fire layout, unrelated body")
    d_occ = dict(number="SYN-VDA/OC/2025/0071", institution="Satpura Valley Institute of Technology",
                 address="12 Synthetic Ridge Road, Itarsi North 461199", issue="20 June 2025", valid=None)
    add("dev_occ", "DEV-C11", "occupancy_certificate", certificate(OCC_DEV, **d_occ, extra=("Built-up Area: 9,800 sq. m",)),
        "different document type, same institution", fields=_fields(d_occ["institution"], d_occ["number"], "2025-06-20"))
    add("dev_blank_a", "DEV-C12", "other", blank_scan(21), "near-blank image-only page", text=False)
    add("dev_blank_b", "DEV-C13", "other", blank_scan(22), "near-blank image-only page", text=False)

    P = FixturePair
    pairs += [
        P("dev_p01", "dev_fire_src", "dev_fire_exact", "reuse", "dev", False, "exact duplicate across cases"),
        P("dev_p02", "dev_fire_src", "dev_fire_meta", "reuse", "dev", False, "metadata-only change"),
        P("dev_p03", "dev_fire_src", "dev_fire_vec", "reuse", "dev", False, "vector rescale + rotation"),
        P("dev_p04", "dev_fire_src", "dev_fire_scan", "reuse", "dev", False, "scan-like raster copy"),
        P("dev_p05", "dev_fire_src", "dev_fire_crop", "reuse", "dev", False, "cropped, brightness/contrast raster"),
        P("dev_p06", "dev_fire_src", "dev_fire_tmpl", "distinct", "dev", True, "same template, different institution"),
        P("dev_p07", "dev_fire_src", "dev_fire_renew", "distinct", "dev", True, "same issuer layout, different number/date"),
        P("dev_p08", "dev_fire_src", "dev_letter", "distinct", "dev", True, "similar logo/border, unrelated body"),
        P("dev_p09", "dev_fire_src", "dev_occ", "distinct", "dev", True, "two documents of the same institution"),
        P("dev_p10", "dev_fire_src", "dev_fire_alter", "altered", "dev", False, "critical-field alteration"),
        P("dev_p11", "dev_blank_a", "dev_blank_b", "distinct", "dev", False, "two near-blank unreadable pages"),
        P("dev_p12", "dev_fire_scan", "dev_fire_tmpl", "distinct", "dev", True, "raster copy vs same-template negative"),
    ]

    # ---------------- held-out split (different issuers, institutions and documents) ----------------
    h_ssc = dict(number="SYN-KSC/2025/0907", institution="Konkan Coast Institute of Engineering",
                 address="88 Synthetic Harbour Road, Ratnagiri South 415699", issue="27 August 2025", valid="26 August 2030")
    add("ho_ssc_src", "HO-C01", "structural_stability_certificate", certificate(STRUCT_HO, **h_ssc), "source",
        fields=_fields(h_ssc["institution"], h_ssc["number"], "2025-08-27"))
    s = docs["ho_ssc_src"].pdf
    ef = docs["ho_ssc_src"].expected_fields
    add("ho_ssc_exact", "HO-C02", "structural_stability_certificate", s, "byte copy of ho_ssc_src", "ho_ssc_src", ef)
    add("ho_ssc_vec", "HO-C03", "structural_stability_certificate", t_vector_rotate_scale(s, 0, 0.7),
        "vector copy: scaled 0.7", "ho_ssc_src", ef)
    add("ho_ssc_vcrop", "HO-C04", "structural_stability_certificate", t_vector_crop(s, 0.04),
        "vector copy: crop box 4% margins", "ho_ssc_src", ef)
    add("ho_ssc_scan", "HO-C05", "structural_stability_certificate",
        t_raster(s, seed=31, rotate_deg=-2.0, scale=0.75, noise=9, blur=3, jpeg=45),
        "raster scan: rotate −2°, scale 0.75, noise σ9, blur 3, JPEG q45 (no text layer)", "ho_ssc_src", ef, text=False)
    add("ho_ssc_rot", "HO-C06", "structural_stability_certificate", t_raster(s, seed=32, quarter_turns=1, jpeg=60),
        "raster: rotated 90°, JPEG q60 (no text layer)", "ho_ssc_src", ef, text=False)
    h_noc = dict(number="SYN-NSU/NOC/2026/0044", institution="Konkan Coast Institute of Engineering",
                 address="88 Synthetic Harbour Road, Ratnagiri South 415699", issue="5 April 2026", valid=None)
    add("ho_noc_src", "HO-C07", "university_noc", certificate(NOC_HO, **h_noc), "source",
        fields=_fields(h_noc["institution"], h_noc["number"], "2026-04-05"))
    add("ho_noc_meta", "HO-C08", "university_noc", t_metadata(docs["ho_noc_src"].pdf), "metadata changed + re-saved",
        "ho_noc_src", docs["ho_noc_src"].expected_fields)
    add("ho_noc_scan", "HO-C09", "university_noc", t_raster(docs["ho_noc_src"].pdf, seed=33, brightness=-20, contrast=1.2,
                                                           crop=0.03, jpeg=50),
        "raster: crop 3%, brightness −20, contrast 1.2, JPEG q50 (no text layer)", "ho_noc_src",
        docs["ho_noc_src"].expected_fields, text=False)
    h_tmpl = dict(h_ssc, number="SYN-KSC/2025/1120", institution="Sahyadri Heights College of Technology",
                  address="3 Synthetic Ghat Lane, Chiplun West 415699", issue="14 October 2025", valid="13 October 2030")
    add("ho_ssc_tmpl", "HO-C10", "structural_stability_certificate", certificate(STRUCT_HO, **h_tmpl),
        "same template, different institution/number/dates",
        fields=_fields(h_tmpl["institution"], h_tmpl["number"], "2025-10-14"))
    h_noc2 = dict(h_noc, number="SYN-NSU/NOC/2024/0012", issue="18 March 2024")
    add("ho_noc_old", "HO-C11", "university_noc", certificate(NOC_HO, **h_noc2),
        "same issuer layout and institution, earlier NOC (different number/date)",
        fields=_fields(h_noc2["institution"], h_noc2["number"], "2024-03-18"))
    add("ho_letter", "HO-C12", "other", letter(LETTER_HO, heading="ANNUAL DRILL CIRCULAR", paragraphs=(
        "All colleges in the Ratnagiri district must conduct two evacuation drills each term (fictional).",
        "Attendance registers and drill timings should be kept for the inspecting officer.",
        "This circular is generated for software evaluation and refers to no real institution.")),
        "same frame and seal as the Konkan fire layout, unrelated body")
    h_fire = dict(number="SYN-KFS/2026/0212", institution="Konkan Coast Institute of Engineering",
                  address="88 Synthetic Harbour Road, Ratnagiri South 415699", issue="2 January 2026", valid="1 January 2029")
    add("ho_fire", "HO-C13", "fire_safety_certificate", certificate(FIRE_HO, **h_fire), "source",
        fields=_fields(h_fire["institution"], h_fire["number"], "2026-01-02"))
    add("ho_ssc_alter", "HO-C14", "structural_stability_certificate",
        certificate(STRUCT_HO, **{**h_ssc, "issue": "27 August 2026", "valid": "26 August 2031"}),
        "ho_ssc_src with issue/valid dates changed (controlled alteration)", "ho_ssc_src",
        _fields(h_ssc["institution"], h_ssc["number"], "2026-08-27"))
    add("ho_blank", "HO-C15", "other", blank_scan(41), "near-blank image-only page", text=False)

    pairs += [
        P("ho_p01", "ho_ssc_src", "ho_ssc_exact", "reuse", "heldout", False, "exact duplicate across cases"),
        P("ho_p02", "ho_ssc_src", "ho_ssc_vec", "reuse", "heldout", False, "vector rescale", hero=True),
        P("ho_p03", "ho_ssc_src", "ho_ssc_vcrop", "reuse", "heldout", False, "vector crop"),
        P("ho_p04", "ho_ssc_src", "ho_ssc_scan", "reuse", "heldout", False, "scan-like raster copy"),
        P("ho_p05", "ho_ssc_src", "ho_ssc_rot", "reuse", "heldout", False, "raster rotated 90°"),
        P("ho_p06", "ho_noc_src", "ho_noc_meta", "reuse", "heldout", False, "metadata-only change"),
        P("ho_p07", "ho_noc_src", "ho_noc_scan", "reuse", "heldout", False, "cropped, brightness/contrast raster"),
        P("ho_p08", "ho_ssc_src", "ho_ssc_tmpl", "distinct", "heldout", True, "same template, different institution", hero=True),
        P("ho_p09", "ho_noc_src", "ho_noc_old", "distinct", "heldout", True, "same issuer layout, different number/date"),
        P("ho_p10", "ho_fire", "ho_letter", "distinct", "heldout", True, "similar logo/border, unrelated body"),
        P("ho_p11", "ho_ssc_src", "ho_noc_src", "distinct", "heldout", True, "two documents of the same institution"),
        P("ho_p12", "ho_ssc_src", "ho_fire", "distinct", "heldout", True, "two documents of the same institution"),
        P("ho_p13", "ho_ssc_src", "ho_ssc_alter", "altered", "heldout", False, "critical-field alteration (dates)"),
        P("ho_p14", "ho_ssc_scan", "ho_blank", "distinct", "heldout", False, "raster copy vs unreadable page"),
        P("ho_p15", "ho_ssc_scan", "ho_ssc_tmpl", "distinct", "heldout", True, "raster copy vs same-template negative"),
        P("ho_p16", "ho_noc_scan", "ho_noc_old", "distinct", "heldout", True, "raster copy vs same-issuer negative"),
    ]
    _tag_v1(pairs)
    _add_v2(docs, pairs, add)
    return Dataset(DATASET_VERSION, docs, pairs)


_V1_TAGS = {
    "exact duplicate across cases": ("exact_copy", "clean"),
    "metadata-only change": ("metadata_resave", "clean"),
    "vector rescale + rotation": ("vector_rescale_rotate", "clean"),
    "vector rescale": ("vector_rescale", "clean"),
    "vector crop": ("vector_crop", "clean"),
    "scan-like raster copy": ("raster_scan", "degraded"),
    "cropped, brightness/contrast raster": ("raster_crop_brightness", "degraded"),
    "raster rotated 90°": ("raster_rotate90", "degraded"),
}


def _tag_v1(pairs: list) -> None:
    for pr in pairs:
        transform, quality = _V1_TAGS.get(pr.scenario, ("n/a", "clean"))
        if pr.label == "altered":
            transform = "field_alteration"
        elif pr.label == "distinct":
            transform = "different_document"
        if "unreadable" in pr.scenario or "near-blank" in pr.scenario:
            quality = "poor"
        elif "raster copy" in pr.scenario:
            quality = "degraded"
        pr.transform, pr.quality = transform, quality


FIRE_D2 = Layout("Synthetic Aravali Fire & Rescue Services (Fictional)", "FIRE SAFETY CERTIFICATE", "AF", (0.55, 0.15, 0.20),
                 body=("Fire alarm panels, extinguishers and emergency lighting were tested on site (fictional).",))
OCC_H2 = Layout("Synthetic Godavari Building Authority (Fictional)", "OCCUPANCY CERTIFICATE", "GB", (0.12, 0.35, 0.45),
                body=("The structure is permitted to be occupied for academic purposes (fictional).",
                      "Occupancy is subject to periodic renewal of the fire safety certificate."))
NOC_H2 = Layout("Synthetic Malabar State University (Fictional)", "NO OBJECTION CERTIFICATE", "MU", (0.40, 0.25, 0.10),
                body=("The University records no objection to the programmes listed in the application (fictional).",))
LETTER_H2 = Layout("Synthetic Godavari Building Authority (Fictional)", "", "GB", (0.12, 0.35, 0.45))


def _add_v2(docs: dict, pairs: list, add) -> None:
    P = FixturePair
    # ---------------- dev2: simulated photographs, poor scans (used for OCR/photo checks; thresholds unchanged) ----
    d2 = dict(number="SYN-AFR/2026/0315", institution="Bhimtal Lakes Institute of Technology",
              address="9 Synthetic Lake Road, Bhimtal 263199", issue="8 May 2026", valid="7 May 2029")
    add("d2_fire_src", "DEV2-C01", "fire_safety_certificate", certificate(FIRE_D2, **d2), "source",
        fields=_fields(d2["institution"], d2["number"], "2026-05-08"))
    src = docs["d2_fire_src"].pdf
    ef = docs["d2_fire_src"].expected_fields
    add("d2_fire_photo", "DEV2-C02", "fire_safety_certificate", t_photo(src, seed=51),
        "simulated photograph: perspective ±6%, lighting gradient 25%, noise σ6, blur 3, JPEG q70", "d2_fire_src", ef, text=False)
    add("d2_fire_photo_strong", "DEV2-C03", "fire_safety_certificate", t_photo(src, seed=52, tilt=0.10, shade=0.4, noise=10, blur=5, jpeg=50),
        "simulated photograph (strong): perspective ±10%, lighting 40%, noise σ10, blur 5, JPEG q50", "d2_fire_src", ef, text=False)
    add("d2_fire_poor", "DEV2-C04", "fire_safety_certificate", t_poor_scan(src, seed=53),
        "poor scan: 45 dpi, blur 7, noise σ22, contrast 0.6, JPEG q25", "d2_fire_src", ef, text=False)
    add("d2_fire_scan", "DEV2-C05", "fire_safety_certificate", t_raster(src, seed=54, rotate_deg=0.8, noise=5, jpeg=65),
        "raster scan: rotate 0.8°, noise σ5, JPEG q65", "d2_fire_src", ef, text=False)
    d2t = dict(d2, institution="Ranikhet Ridge College of Engineering", number="SYN-AFR/2026/0377",
               address="14 Synthetic Pine Avenue, Ranikhet 263699", issue="19 May 2026", valid="18 May 2029")
    add("d2_fire_tmpl_photo", "DEV2-C06", "fire_safety_certificate", t_photo(certificate(FIRE_D2, **d2t), seed=55),
        "simulated photograph of a same-template certificate for a different institution",
        fields=_fields(d2t["institution"], d2t["number"], "2026-05-19"), text=False)
    pairs += [
        P("d2_p01", "d2_fire_src", "d2_fire_photo", "reuse", "dev2", False, "simulated photograph", transform="photo_sim", quality="degraded"),
        P("d2_p02", "d2_fire_src", "d2_fire_photo_strong", "reuse", "dev2", False, "simulated photograph (strong)", transform="photo_sim_strong", quality="poor"),
        P("d2_p03", "d2_fire_src", "d2_fire_poor", "reuse", "dev2", False, "poor scan", transform="poor_scan", quality="poor"),
        P("d2_p04", "d2_fire_src", "d2_fire_scan", "reuse", "dev2", False, "raster scan", transform="raster_scan", quality="degraded"),
        P("d2_p05", "d2_fire_src", "d2_fire_tmpl_photo", "distinct", "dev2", True, "photo of same-template negative",
          transform="different_document", quality="degraded"),
        P("d2_p06", "d2_fire_photo", "d2_fire_tmpl_photo", "distinct", "dev2", True, "two photos, same template",
          transform="different_document", quality="degraded"),
    ]

    # ---------------- heldout2: fresh issuers/institutions/documents (evaluated once, after v3 was frozen) ----------
    h_occ = dict(number="SYN-GBA/OC/2025/0544", institution="Nashik Vineyard Institute of Engineering",
                 address="31 Synthetic Vine Road, Nashik 422099", issue="11 November 2025", valid=None)
    add("h2_occ_src", "HO2-C01", "occupancy_certificate", certificate(OCC_H2, **h_occ, extra=("Built-up Area: 7,350 sq. m",)),
        "source", fields=_fields(h_occ["institution"], h_occ["number"], "2025-11-11"))
    s2 = docs["h2_occ_src"].pdf
    e2 = docs["h2_occ_src"].expected_fields
    add("h2_occ_exact", "HO2-C02", "occupancy_certificate", s2, "byte copy of h2_occ_src", "h2_occ_src", e2)
    add("h2_occ_meta", "HO2-C03", "occupancy_certificate", t_metadata(s2), "metadata changed + re-saved", "h2_occ_src", e2)
    add("h2_occ_photo", "HO2-C04", "occupancy_certificate", t_photo(s2, seed=61, tilt=0.07),
        "simulated photograph: perspective ±7%, lighting 25%, noise σ6, blur 3, JPEG q70", "h2_occ_src", e2, text=False)
    add("h2_occ_scan", "HO2-C05", "occupancy_certificate", t_raster(s2, seed=62, rotate_deg=1.5, scale=0.85, noise=7, jpeg=55),
        "raster scan: rotate 1.5°, scale 0.85, noise σ7, JPEG q55", "h2_occ_src", e2, text=False)
    add("h2_occ_rot", "HO2-C06", "occupancy_certificate", t_raster(s2, seed=63, quarter_turns=3, jpeg=60),
        "raster rotated 270°, JPEG q60", "h2_occ_src", e2, text=False)
    add("h2_occ_poor", "HO2-C07", "occupancy_certificate", t_poor_scan(s2, seed=64), "poor scan", "h2_occ_src", e2, text=False)
    h_tmpl = dict(h_occ, institution="Aurangabad Caves College of Technology", number="SYN-GBA/OC/2025/0610",
                  address="2 Synthetic Ellora Lane, Aurangabad 431099", issue="2 December 2025")
    add("h2_occ_tmpl", "HO2-C08", "occupancy_certificate", certificate(OCC_H2, **h_tmpl, extra=("Built-up Area: 6,900 sq. m",)),
        "same template, different institution/number/date",
        fields=_fields(h_tmpl["institution"], h_tmpl["number"], "2025-12-02"))
    h_old = dict(h_occ, number="SYN-GBA/OC/2022/0101", issue="4 February 2022")
    add("h2_occ_old", "HO2-C09", "occupancy_certificate", certificate(OCC_H2, **h_old, extra=("Built-up Area: 7,350 sq. m",)),
        "same issuer layout and institution, earlier certificate", fields=_fields(h_old["institution"], h_old["number"], "2022-02-04"))
    add("h2_occ_alter", "HO2-C10", "occupancy_certificate",
        certificate(OCC_H2, **{**h_occ, "number": "SYN-GBA/OC/2025/0545"}, extra=("Built-up Area: 7,350 sq. m",)),
        "h2_occ_src with certificate number changed", "h2_occ_src", _fields(h_occ["institution"], "SYN-GBA/OC/2025/0545", "2025-11-11"))
    add("h2_letter", "HO2-C11", "other", letter(LETTER_H2, heading="BUILDING SAFETY AWARENESS WEEK", paragraphs=(
        "All academic buildings in the Nashik circle will host safety demonstrations (fictional).",
        "Principals should nominate a safety coordinator and share evacuation plans with staff.",
        "This circular is generated for software evaluation and refers to no real institution.")),
        "same frame and seal as the occupancy layout, unrelated body")
    h_noc = dict(number="SYN-MSU/NOC/2026/0088", institution="Nashik Vineyard Institute of Engineering",
                 address="31 Synthetic Vine Road, Nashik 422099", issue="20 March 2026", valid=None)
    add("h2_noc", "HO2-C12", "university_noc", certificate(NOC_H2, **h_noc), "different document, same institution",
        fields=_fields(h_noc["institution"], h_noc["number"], "2026-03-20"))
    add("h2_blank", "HO2-C13", "other", blank_scan(71), "near-blank image-only page", text=False)
    pairs += [
        P("h2_p01", "h2_occ_src", "h2_occ_exact", "reuse", "heldout2", False, "exact duplicate", transform="exact_copy"),
        P("h2_p02", "h2_occ_src", "h2_occ_meta", "reuse", "heldout2", False, "metadata-only change", transform="metadata_resave"),
        P("h2_p03", "h2_occ_src", "h2_occ_photo", "reuse", "heldout2", False, "simulated photograph", transform="photo_sim", quality="degraded"),
        P("h2_p04", "h2_occ_src", "h2_occ_scan", "reuse", "heldout2", False, "raster scan", transform="raster_scan", quality="degraded"),
        P("h2_p05", "h2_occ_src", "h2_occ_rot", "reuse", "heldout2", False, "raster rotated 270°", transform="raster_rotate270", quality="degraded"),
        P("h2_p06", "h2_occ_src", "h2_occ_poor", "reuse", "heldout2", False, "poor scan", transform="poor_scan", quality="poor"),
        P("h2_p07", "h2_occ_src", "h2_occ_tmpl", "distinct", "heldout2", True, "same template, different institution", transform="different_document"),
        P("h2_p08", "h2_occ_src", "h2_occ_old", "distinct", "heldout2", True, "same issuer layout, different number/date", transform="different_document"),
        P("h2_p09", "h2_occ_src", "h2_letter", "distinct", "heldout2", True, "similar seal/border, unrelated body", transform="different_document"),
        P("h2_p10", "h2_occ_src", "h2_noc", "distinct", "heldout2", True, "two documents of the same institution", transform="different_document"),
        P("h2_p11", "h2_occ_src", "h2_occ_alter", "altered", "heldout2", False, "certificate number changed", transform="field_alteration"),
        P("h2_p12", "h2_occ_photo", "h2_occ_tmpl", "distinct", "heldout2", True, "photo vs same-template negative", transform="different_document", quality="degraded"),
        P("h2_p13", "h2_occ_scan", "h2_blank", "distinct", "heldout2", False, "raster copy vs unreadable page", transform="different_document", quality="poor"),
    ]


def dataset_digest(ds: Dataset) -> str:
    h = hashlib.sha256()
    for key in sorted(ds.docs):
        h.update(key.encode())
        h.update(hashlib.sha256(ds.docs[key].pdf).digest())
    return h.hexdigest()[:16]
