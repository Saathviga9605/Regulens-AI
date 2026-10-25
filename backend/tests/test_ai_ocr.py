"""Deliverable 8: local OCR providers, evidence coordinates, OCR-aware extraction, fusion and explanations."""

import json
import re
from pathlib import Path

import pymupdf
import pytest

from app.core.config import Settings
from app.models.enums import PageExtractionMethod, PageStatus
from app.services import extraction, ocr as ocr_service, pdf_text, reuse_engine as engine
from app.services.ocr import OcrLine, OcrPage, parse_tesseract_tsv
from app.services.reuse_dataset import build_dataset
from app.services.reuse_eval import fixture_input
from tests.conftest import make_settings


class FakeOcr:
    """Deterministic stand-in for an OCR engine (records the rotations it was asked for)."""

    name = "fake"
    available = True

    def __init__(self, pages: dict[int, OcrPage]):
        self.pages = pages
        self.calls: list[int] = []

    def engine_version(self) -> str:
        return "fake 1"

    def recognize(self, png: bytes) -> str:
        return self.recognize_detailed(png).text

    def recognize_detailed(self, png: bytes) -> OcrPage:
        rotation = [0, 90, 180, 270][len(self.calls) % 4]
        self.calls.append(rotation)
        page = self.pages.get(rotation) or OcrPage("", [], "fake", "fake 1")
        return OcrPage(page.text, list(page.lines), "fake", "fake 1")


def _image_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    pix = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 300, 300), False)
    pix.set_rect(pix.irect, (255,))
    page.insert_image(page.rect, pixmap=pix)
    path = tmp_path / "scan.pdf"
    path.write_bytes(doc.tobytes())
    return path


def _lines(*rows: tuple[str, float]) -> list[OcrLine]:
    return [OcrLine(t, c, [0.1, 0.1 + i * 0.05, 0.8, 0.14 + i * 0.05]) for i, (t, c) in enumerate(rows)]


def test_ocr_page_keeps_confidence_coordinates_and_engine(tmp_path):
    lines = _lines(("CertificateNo.:SYN-ABC/2026/0001", 0.95), ("DateofIssue:3March2026", 0.9),
                   ("Nameof Institution:Fictional College", 0.92))
    fake = FakeOcr({0: OcrPage("\n".join(ln.text for ln in lines), lines, "fake", "fake 1")})
    result = pdf_text.extract_text(_image_pdf(tmp_path), fake, min_chars=20, max_pages=5, dpi=100)
    page = result.pages[0]
    assert page.method == PageExtractionMethod.OCR and page.status == PageStatus.OK
    assert page.ocr_engine == "fake" and 0.9 <= page.ocr_confidence <= 0.95
    assert page.lines[0]["box"] == [0.1, 0.1, 0.8, 0.14] and page.lines[0]["confidence"] == 0.95
    assert fake.calls == [0]  # a confident upright reading triggers no rotation retries


def test_rotation_is_retried_only_when_the_upright_reading_is_weak(tmp_path):
    good = _lines(("CertificateNo.:SYN-ABC/2026/0001", 0.95), ("Valid Until: 2 March 2029", 0.93))
    fake = FakeOcr({0: OcrPage("x", _lines(("x", 0.2)), "fake", "fake 1"),
                    90: OcrPage("\n".join(ln.text for ln in good), good, "fake", "fake 1")})
    page = pdf_text.extract_text(_image_pdf(tmp_path), fake, min_chars=20, max_pages=5, dpi=100).pages[0]
    assert fake.calls == [0, 90, 180, 270]
    assert page.rotation_degrees == 90 and "rotated" in " ".join(page.warnings)


def test_low_confidence_page_is_flagged(tmp_path):
    weak = _lines(("Certificate No.: SYN-ABC/2026/0001 lots of text here", 0.65))
    fake = FakeOcr({r: OcrPage(weak[0].text, weak, "fake", "fake 1") for r in (0, 90, 180, 270)})
    page = pdf_text.extract_text(_image_pdf(tmp_path), fake, min_chars=20, max_pages=5, dpi=100).pages[0]
    assert any("Low OCR confidence" in w for w in page.warnings)


def test_unavailable_ocr_stays_honest(tmp_path):
    result = pdf_text.extract_text(_image_pdf(tmp_path), ocr_service.NoOcr(), min_chars=20, max_pages=5, dpi=100)
    assert result.status.value == "failed" and result.failure_code == "ocr_unavailable"
    assert result.pages[0].ocr_engine is None and result.pages[0].lines == []


def test_text_layer_pages_get_line_coordinates_without_ocr(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), "Certificate No.: SYN-XYZ/2026/0042", fontsize=12)
    page.insert_text((60, 130), "This line pads the page so the text layer is long enough to use.", fontsize=12)
    path = tmp_path / "text.pdf"
    path.write_bytes(doc.tobytes())
    called = FakeOcr({})
    result = pdf_text.extract_text(path, called, min_chars=20, max_pages=5, dpi=100)
    p = result.pages[0]
    assert p.method == PageExtractionMethod.TEXT_LAYER and called.calls == []  # clean text pages are never OCR'd
    first = next(ln for ln in p.lines if "SYN-XYZ" in ln["text"])
    assert first["confidence"] is None and 0 < first["box"][0] < first["box"][2] <= 1 and first["box"][1] < 0.2


def test_tesseract_tsv_is_grouped_into_lines():
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t10\t20\t40\t10\t96\tCertificate\n"
           "5\t1\t1\t1\t1\t2\t55\t20\t30\t10\t90\tNo.:\n"
           "5\t1\t1\t1\t2\t1\t10\t40\t80\t10\t-1\t\n"
           "5\t1\t1\t1\t2\t2\t10\t40\t80\t10\t70\tSYN-1\n")
    lines = parse_tesseract_tsv(tsv, 100, 100)
    assert [ln.text for ln in lines] == ["Certificate No.:", "SYN-1"]
    assert lines[0].confidence == pytest.approx(0.93) and lines[0].box == [0.1, 0.2, 0.85, 0.3]


def test_provider_selection_is_explicit_and_local(tmp_path):
    s = lambda **kw: make_settings(tmp_path / "x.db", **kw)  # noqa: E731
    assert ocr_service.build_ocr_engine(s(ocr_engine="none")).name == "none"
    assert ocr_service.build_ocr_engine(s(ocr_enabled=False, ocr_engine="rapidocr")).name == "none"
    t = ocr_service.build_ocr_engine(s(ocr_engine="tesseract", tesseract_cmd=str(tmp_path / "missing.exe")))
    assert t.name == "tesseract" and t.available is False  # explicitly requested but absent: reported, not replaced
    auto = ocr_service.build_ocr_engine(s(ocr_engine="auto", tesseract_cmd=str(tmp_path / "missing.exe")))
    assert auto.name in ("rapidocr", "none")
    assert ocr_service.describe(auto)["local_only"] is True
    with pytest.raises(Exception):
        make_settings(tmp_path / "x.db", ocr_engine="cloud")


def test_extraction_tolerates_ocr_spacing_and_records_evidence():
    text = "CertificateNo.:SYN-KSC/2025/0907\nDateofIssue:27August2025\nNameof Institution:Konkan Coast Instituteof Engineering"
    lines = [{"text": t, "confidence": c, "box": [0.1, 0.1 * i, 0.7, 0.1 * i + 0.03]}
             for i, (t, c) in enumerate(zip(text.split("\n"), (0.93, 0.62, 0.9)), start=1)]
    page = extraction.PageInput(1, text, PageExtractionMethod.OCR, lines)
    got = {f.field_name: f for f in extraction.extract_fields([page], set())}
    cert = got["certificate_number"]
    assert cert.raw_value == "SYN-KSC/2025/0907" and cert.evidence_source == "ocr"
    assert cert.evidence_box == [0.1, 0.1, 0.7, 0.13] and cert.ocr_confidence == 0.93 and cert.confidence.value == "medium"
    date = got["issue_date"]
    assert date.normalized_value == {"date": "2025-08-27"}  # "27August2025" parsed
    assert date.confidence.value == "low" and any("Low OCR confidence" in w for w in date.warnings)


def test_low_confidence_ocr_conflict_is_inconclusive_not_a_conflict():
    page = engine.PageText(1, "Certificate No.: A-1", "ok", "text_layer")
    ocr_page = engine.PageText(1, "CertificateNo.:A-7", "ok", "ocr", 0.7)
    a = engine.DocumentInput("a", "c1", "0" * 64, b"", [page], [engine.FieldEvidence(
        "certificate_number", "A-1", {"text": "A1"}, 1, "Certificate No.: A-1", "extracted", "text_layer", [0, 0, 1, 1], None)])
    b = engine.DocumentInput("b", "c2", "1" * 64, b"", [ocr_page], [engine.FieldEvidence(
        "certificate_number", "A-7", {"text": "A7"}, 1, "CertificateNo.:A-7", "extracted", "ocr", [0, 0, 1, 1], 0.6)])
    c = engine.field_stage(a, b)["comparisons"][0]
    assert c["outcome"] == "inconclusive" and "misread" in c["explanation"]


@pytest.fixture(scope="module")
def ds():
    return build_dataset()


def test_whitespace_insensitive_text_and_region_mapping(ds):
    a = fixture_input(ds.docs["dev_fire_src"], None)
    b = fixture_input(ds.docs["dev_fire_alter"], None)
    r = engine.compare(a, b)
    assert r.outcome == engine.CANDIDATE
    cert = next(c for c in r.fields["comparisons"] if c["field"] == "certificate_number")
    assert cert["outcome"] == "conflict" and cert["visual_difference"] is True  # the changed number is where pixels differ
    assert r.fusion["regions"]["regions_on_critical_fields"] >= 1
    assert any(s["signal"] == "field_regions" for s in r.fusion["contradicting"])
    squashed = engine.DocumentInput("x", "c", "2" * 64, b"", [engine.PageText(1, re.sub(r" ", "", a.pages[0].text))], [])
    assert engine.text_stage(a, squashed, engine.DEFAULT_CONFIG)["jaccard"] > 0.95  # OCR-style spacing loss


def test_explanation_statements_are_traceable_to_stored_evidence(ds):
    r = engine.compare(fixture_input(ds.docs["dev_fire_src"], None), fixture_input(ds.docs["dev_fire_tmpl"], None))
    evidence = {"exact": r.exact, "text": r.text, "visual": r.visual, "geometric": r.geometric, "fields": r.fields}
    blob = json.dumps(evidence, default=str)
    assert r.outcome == engine.NOT_MATCHED and r.explanation["generator"] == "deterministic"
    assert r.explanation["rule"] == r.fusion["rule"]
    for st in r.explanation["statements"]:
        for path, value in st["refs"].items():
            if value is not None and not isinstance(value, bool):
                assert json.dumps(value, default=str).strip('"') in blob, (path, value)  # cited value exists in the record
        for number in re.findall(r"\d+\.\d+", st["text"]):
            assert number in blob, number  # no invented metrics
        for quote in re.findall("“([^”]+)”", st["text"]):
            assert quote in blob, quote  # no invented quotes
    kinds = {s["kind"] for s in r.explanation["statements"]}
    assert "contradicts" in kinds


def test_low_quality_ocr_text_cannot_confirm(ds):
    a = fixture_input(ds.docs["dev_fire_src"], None)
    b = fixture_input(ds.docs["dev_fire_meta"], None)
    for p in b.pages:
        p.method, p.ocr_confidence = "ocr", 0.4
    t = engine.text_stage(a, b, engine.DEFAULT_CONFIG)
    assert t["low_quality"] is True and "low confidence" in t["quality_note"]
    out, reasons, _ = engine.decide(engine.exact_stage(a, b), t, {"status": "unavailable", "reason": "x"},
                                    {"status": "inconclusive", "reason": "x"},
                                    {"comparisons": [], "agree": 0, "conflict": 0, "inconclusive": 0}, engine.DEFAULT_CONFIG)
    assert out != engine.MATCH_CONFIRMED


def test_photo_rectification_brings_photographs_within_retrieval(ds):
    a = fixture_input(ds.docs["d2_fire_src"], None)
    b = fixture_input(ds.docs["d2_fire_photo"], None)
    v = engine.visual_stage(a, b, engine.DEFAULT_CONFIG)
    assert v["status"] == "computed" and v["distance"] <= engine.DEFAULT_CONFIG.phash_candidate
    assert any(d.rectified for d in b.descriptors(engine.DEFAULT_CONFIG))
    assert not any(d.rectified for d in a.descriptors(engine.DEFAULT_CONFIG))


rapid = ocr_service.RapidOcrEngine()


@pytest.mark.skipif(not rapid.available, reason="rapidocr-onnxruntime not installed")
def test_real_local_ocr_reads_a_scanned_certificate(ds):
    inp = fixture_input(ds.docs["dev_fire_scan"], rapid)
    assert inp.pages[0].method == "ocr" and inp.pages[0].ocr_confidence > 0.8
    cert = next(f for f in inp.fields if f.field_name == "certificate_number")
    assert cert.raw_value == "SYN-VFS/2026/0418" and cert.evidence_source == "ocr" and cert.evidence_box
    r = engine.compare(fixture_input(ds.docs["dev_fire_src"], None), inp)
    assert r.outcome == engine.MATCH_CONFIRMED and r.text["provenance"]["b"]["ocr_pages"] == 1


@pytest.mark.skipif(not rapid.available, reason="rapidocr-onnxruntime not installed")
def test_poor_scan_is_not_confirmed_even_with_ocr(ds):
    r = engine.compare(fixture_input(ds.docs["d2_fire_src"], None), fixture_input(ds.docs["d2_fire_poor"], rapid))
    assert r.outcome in (engine.INCONCLUSIVE, engine.CANDIDATE)


def test_processing_cache_is_keyed_by_checksum_and_pipeline_version(client, code):
    from sqlalchemy import select

    from app.models import DocumentProcessing
    from app.services import processing
    from tests.test_documents import upload

    doc = upload(client, code, build_dataset().docs["dev_fire_src"].pdf, name="cert.pdf").json()
    assert client.post(f"/api/v1/documents/{doc['id']}/processing").status_code in (200, 201)
    with client.app.state.session_factory() as session:
        row = session.execute(select(DocumentProcessing).where(DocumentProcessing.document_id == doc["id"])).scalar_one()
        assert row.pipeline_version == processing.PIPELINE_VERSION and "label_regex_v2" in row.pipeline_version
        assert row.pages[0].lines and row.fields
        first_id = row.id
        row.pipeline_version = "p1+old"  # simulate a result from an older pipeline
        session.commit()
    assert client.post(f"/api/v1/documents/{doc['id']}/processing").status_code in (200, 201)
    with client.app.state.session_factory() as session:
        row = session.execute(select(DocumentProcessing).where(DocumentProcessing.document_id == doc["id"])).scalar_one()
        assert row.id != first_id and row.pipeline_version == processing.PIPELINE_VERSION  # re-processed, not reused
        cert = next(f for f in row.fields if f.field_name == "certificate_number")
        assert cert.evidence_source == "text_layer" and cert.evidence_box and cert.ocr_confidence is None
