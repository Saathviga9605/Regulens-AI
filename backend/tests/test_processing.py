"""Text extraction, OCR fallback, classification, evidence-grounded extraction and caching."""

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.models import Document, ExtractedField
from app.models.enums import DocumentCategory as C, PageExtractionMethod as M
from app.services import classification, demo_documents as demo, processing
from app.services.extraction import PageInput, extract_fields
from app.services.normalize import is_grounded, parse_area, parse_date, text_similarity
from app.services.pdf_text import OcrError, TesseractOcr, resolve_tesseract
from tests.test_documents import upload


class FakeOcr:
    name = "fake"
    available = True

    def __init__(self, text: str = "", fail: bool = False) -> None:
        self.text, self.fail, self.calls = text, fail, 0

    def recognize(self, png: bytes) -> str:
        self.calls += 1
        assert png.startswith(b"\x89PNG")
        if self.fail:
            raise OcrError("OCR timed out for this page.")
        return self.text


@pytest.fixture
def no_ocr(app):
    app.state.ocr_engine = TesseractOcr(None)
    return app.state.ocr_engine


def process(client, doc_id: str, **params):
    return client.post(f"/api/v1/documents/{doc_id}/processing", params=params)


def two_page_pdf() -> bytes:
    d = pymupdf.open()
    for text in ("FIRE SAFETY CERTIFICATE\nCertificate No.: SYN-1/2026\nName of Institution: Test Synthetic Institute",
                 "Page two\nValid Until: 30 November 2030\nDate of Issue: 14 March 2026"):
        d.new_page().insert_text((72, 72), text, fontsize=11)
    return d.tobytes()


# --- text extraction & OCR ----------------------------------------------------------------------

def test_text_pdf_extracts_pages_with_one_based_numbers(client, code, no_ocr) -> None:
    doc = upload(client, code, two_page_pdf()).json()
    body = process(client, doc["id"]).json()
    assert body["status"] == "completed"
    assert [p["page_number"] for p in body["pages"]] == [1, 2]
    assert {p["method"] for p in body["pages"]} == {"text_layer"}
    fields = {f["field_name"]: f for f in body["fields"]}
    assert fields["valid_until"]["page_number"] == 2
    assert fields["certificate_number"]["page_number"] == 1
    pages = client.get(f"/api/v1/documents/{doc['id']}/pages").json()
    assert pages["total"] == 2 and "Valid Until: 30 November 2030" in pages["items"][1]["text"]


@pytest.mark.parametrize(
    ("category", "heading"),
    [("building_license", "BUILDING LICENSE"), ("form_d", "FORM D")],
)
def test_aph_alternative_document_categories_process_and_classify(client, code, no_ocr, category, heading) -> None:
    content = demo.build_pdf([heading, "Certificate No.: SYN-1", "Valid Until: 30 November 2030"])
    document = upload(client, code, content, category=category).json()
    result = process(client, document["id"]).json()
    assert result["status"] == "completed"
    assert result["classification"]["predicted_category"] == category
    fields = {field["field_name"]: field for field in result["fields"]}
    assert fields["valid_until"]["normalized_value"]["date"] == "2030-11-30"


def test_ocr_unavailable_is_not_a_successful_empty_extraction(client, code, no_ocr, storage) -> None:
    content = demo.build_pdf(demo.FIRE_A, image_only=True, title="scan")
    doc = upload(client, code, content, name="scan.pdf").json()
    body = process(client, doc["id"]).json()
    assert body["status"] == "failed"
    assert body["failure_code"] == "ocr_unavailable"
    assert body["ocr_available"] is False
    assert body["pages"][0]["status"] == "insufficient_text"
    assert body["fields"] == []
    assert str(storage.root) not in str(body) and "Traceback" not in str(body)


def test_ocr_fallback_used_for_image_only_pages(client, code, app) -> None:
    ocr = FakeOcr("FIRE SAFETY CERTIFICATE\nCertificate No.: SYN-OCR/2026/7\nValid Until: 13 March 2029\n")
    app.state.ocr_engine = ocr
    doc = upload(client, code, demo.build_pdf(demo.FIRE_A, image_only=True, title="scan"), name="scan.pdf").json()
    body = process(client, doc["id"]).json()
    assert ocr.calls == 1
    assert body["status"] == "completed_with_warnings"  # OCR text is less reliable
    assert body["pages"][0]["method"] == "ocr" and body["pages"][0]["status"] == "ok"
    cert = next(f for f in body["fields"] if f["field_name"] == "certificate_number")
    assert cert["raw_value"] == "SYN-OCR/2026/7" and cert["confidence"] == "medium"


def test_ocr_failure_reported(client, code, app) -> None:
    app.state.ocr_engine = FakeOcr(fail=True)
    doc = upload(client, code, demo.build_pdf(demo.FIRE_A, image_only=True, title="scan"), name="scan.pdf").json()
    body = process(client, doc["id"]).json()
    assert body["status"] == "failed" and body["failure_code"] == "no_readable_text"
    assert body["pages"][0]["status"] == "ocr_failed"
    assert "OCR timed out" in body["pages"][0]["warnings"][0]


@pytest.mark.skipif(resolve_tesseract("") is None, reason="Tesseract is not installed on this machine")
def test_real_tesseract_ocr(client, code, app, settings) -> None:  # pragma: no cover - depends on local install
    app.state.ocr_engine = TesseractOcr.from_settings(settings)
    doc = upload(client, code, demo.build_pdf(demo.FIRE_A, image_only=True, title="scan"), name="scan.pdf").json()
    body = process(client, doc["id"]).json()
    assert body["pages"][0]["method"] == "ocr"
    assert "FIRE" in client.get(f"/api/v1/documents/{doc['id']}/pages").json()["items"][0]["text"].upper()


def test_tesseract_resolution_never_raises() -> None:
    assert resolve_tesseract("definitely-not-a-real-binary-xyz") is None
    assert TesseractOcr(None).available is False
    with pytest.raises(OcrError):
        TesseractOcr(None).recognize(b"x")


@pytest.mark.parametrize(("content", "code_expected"), [
    (b"%PDF-1.4\nthis is not really a pdf\n%%EOF\n", {"unreadable_pdf", "empty_pdf"}),
    (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
     b"trailer<</Root 1 0 R>>\n%%EOF\n", {"empty_pdf", "unreadable_pdf"}),
    (demo.build_pdf(demo.FIRE_A, encrypt=True, title="x"), {"encrypted_pdf"}),
])
def test_corrupt_empty_and_encrypted_pdfs_fail_safely(client, code, no_ocr, content, code_expected) -> None:
    doc = upload(client, code, content).json()
    body = process(client, doc["id"]).json()
    assert body["status"] == "failed"
    assert body["failure_code"] in code_expected
    assert body["failure_reason"] and "Traceback" not in body["failure_reason"]


def test_missing_stored_file(client, code, storage, no_ocr) -> None:
    from tests.test_documents import stored_files

    doc = upload(client, code).json()
    stored_files(storage)[0].unlink()
    body = process(client, doc["id"]).json()
    assert body["status"] == "failed" and body["failure_code"] == "content_unavailable"


def test_processing_not_found_and_not_processed(client, code) -> None:
    assert process(client, "nope").status_code == 404
    doc = upload(client, code).json()
    response = client.get(f"/api/v1/documents/{doc['id']}/processing")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_processed"
    assert client.get(f"/api/v1/documents/{doc['id']}/pages").status_code == 404
    assert client.get("/api/v1/documents/nope/processing").json()["error"]["code"] == "not_found"


def test_processing_status_after_processing_and_without_sign_in(client, code, anon, no_ocr) -> None:
    doc = upload(client, code, demo.build_pdf(demo.OCC_A, title="occ")).json()
    assert process(client, doc["id"]).status_code == 200
    stored = client.get(f"/api/v1/documents/{doc['id']}/processing")
    assert stored.status_code == 200 and stored.json()["document_id"] == doc["id"]
    # unauthenticated callers are refused before the document is even looked up
    for path in (f"/api/v1/documents/{doc['id']}/processing", "/api/v1/documents/nope/processing"):
        assert anon.get(path).status_code == 401


# --- caching -------------------------------------------------------------------------------------

def test_results_cached_by_checksum_and_pipeline_version(client, code, no_ocr, monkeypatch) -> None:
    content = demo.build_pdf(demo.OCC_A, title="occ")
    doc = upload(client, code, content).json()
    first = process(client, doc["id"]).json()
    again = process(client, doc["id"]).json()
    assert again["reused_from_cache"] is True and again["finished_at"] == first["finished_at"]
    forced = process(client, doc["id"], force=True).json()
    assert forced["finished_at"] != first["finished_at"]
    # Identical content uploaded again (duplicate) reuses the result instead of re-extracting.
    dup = upload(client, code, content, name="copy.pdf").json()
    reused = process(client, dup["id"]).json()
    assert reused["reused_from_cache"] is True and reused["fields"][0]["document_id"] == dup["id"]
    # A pipeline version change makes stored results stale and triggers reprocessing.
    monkeypatch.setattr(processing, "PIPELINE_VERSION", "p2-test")
    assert client.get(f"/api/v1/documents/{doc['id']}/processing").json()["is_current"] is False
    refreshed = process(client, doc["id"]).json()
    assert refreshed["pipeline_version"] == "p2-test" and refreshed["reused_from_cache"] is False


def test_processing_removed_with_document(client, code, app, no_ocr) -> None:
    doc = upload(client, code).json()
    process(client, doc["id"])
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 204
    with app.state.session_factory() as s:
        assert s.query(ExtractedField).count() == 0


# --- classification ------------------------------------------------------------------------------

@pytest.mark.parametrize(("lines", "expected"), [
    (demo.FIRE_A, C.FIRE_SAFETY_CERTIFICATE), (demo.OCC_A, C.OCCUPANCY_CERTIFICATE),
    (demo.SSC_A, C.STRUCTURAL_STABILITY_CERTIFICATE), (demo.TRUST_A, C.TRUST_RESOLUTION),
    (demo.PLAN_B, C.BUILDING_PLAN), (demo.NOC_C, C.UNIVERSITY_NOC), (demo.COMPLETION_C, C.COMPLETION_CERTIFICATE),
])
def test_classifier_recognises_supported_types(lines, expected) -> None:
    result = classification.classify(["\n".join(lines)])
    assert result.predicted_category == expected
    assert result.confidence in ("high", "medium")
    assert result.signals and all("signal" in s for s in result.signals)


def test_uncertain_classification_is_a_valid_outcome() -> None:
    result = classification.classify(["Minutes of a general meeting held on a Tuesday. Tea was served."])
    assert result.predicted_category is None and result.confidence == "uncertain"
    mixed = classification.classify(["FIRE SAFETY CERTIFICATE\nOCCUPANCY CERTIFICATE\nfit for occupation\n"])
    assert mixed.confidence != "high" and mixed.alternatives


def test_mismatch_creates_warning_but_keeps_selected_category(client, code, app, no_ocr) -> None:
    doc = upload(client, code, demo.build_pdf(demo.TRUST_A, title="t"), category="university_noc").json()
    body = process(client, doc["id"]).json()
    assert body["classification"]["predicted_category"] == "trust_resolution"
    assert body["classification"]["selected_category"] == "university_noc"
    assert body["classification"]["agrees_with_selected"] is False
    assert any("differs from the predicted" in w for w in body["warnings"])
    with app.state.session_factory() as s:
        assert s.get(Document, doc["id"]).category == C.UNIVERSITY_NOC
    listed = client.get(f"/api/v1/applications/{code}/documents").json()["items"][0]["processing"]
    assert listed["predicted_category"] == "trust_resolution" and listed["status"] == "completed"


# --- extraction & grounding -----------------------------------------------------------------------

def test_every_extracted_field_is_grounded_in_its_page(client, code, no_ocr) -> None:
    doc = upload(client, code, demo.build_pdf(demo.FIRE_A, title="f")).json()
    body = process(client, doc["id"]).json()
    pages = {p["page_number"]: p["text"] for p in client.get(f"/api/v1/documents/{doc['id']}/pages").json()["items"]}
    extracted = [f for f in body["fields"] if f["status"] == "extracted"]
    assert {f["field_name"] for f in extracted} >= {"certificate_number", "institution_name", "issuing_authority",
                                                     "issue_date", "valid_until", "survey_number", "address"}
    for f in extracted:
        assert is_grounded(f["evidence_quote"], pages[f["page_number"]])
        assert f["raw_value"] in f["evidence_quote"]
        assert f["method"] == "label_regex_v2" and f["confidence"] == "high"
    by = {f["field_name"]: f for f in extracted}
    assert by["valid_until"]["normalized_value"] == {"date": "2029-03-13"}
    assert by["valid_until"]["raw_value"] == "13 March 2029"


def test_grounding_check_rejects_quotes_not_in_text() -> None:
    page = "Certificate No.:   SYN-1/2026\nValid  Until: 1 May 2030"
    assert is_grounded("Certificate No.: SYN-1/2026", page)  # whitespace-only differences allowed
    assert not is_grounded("Certificate No.: SYN-9/2026", page)
    assert not is_grounded("Valid Until: 1 May 2031", page)
    assert not is_grounded("", page) and not is_grounded(None, page)


def test_missing_and_ambiguous_fields() -> None:
    text = ("FIRE SAFETY CERTIFICATE\nCertificate No.: A-1\nCertificate No.: B-2\n"
            "Date of Issue: 05/06/2026\nName of Institution: X Synthetic College\n")
    fields = {f.field_name: f for f in extract_fields([PageInput(1, text, M.TEXT_LAYER)], {C.FIRE_SAFETY_CERTIFICATE})}
    assert fields["certificate_number"].status.value == "ambiguous"
    assert {c["value"] for c in fields["certificate_number"].candidates} == {"A-1", "B-2"}
    assert fields["issue_date"].status.value == "ambiguous"
    assert fields["issue_date"].raw_value == "05/06/2026" and fields["issue_date"].normalized_value is None
    # Never fabricated: absent fields are reported as not found with no value.
    for name in ("valid_until", "issuing_authority", "survey_number"):
        assert fields[name].status.value == "not_found" and fields[name].raw_value is None
        assert fields[name].evidence_quote is None


def test_no_validity_date_is_inferred(client, code, no_ocr) -> None:
    lines = [line for line in demo.FIRE_A if not line.startswith("Valid Until")]
    doc = upload(client, code, demo.build_pdf(lines, title="f")).json()
    fields = {f["field_name"]: f for f in process(client, doc["id"]).json()["fields"]}
    assert fields["valid_until"]["status"] == "not_found" and fields["valid_until"]["normalized_value"] is None


# --- normalisation -------------------------------------------------------------------------------

@pytest.mark.parametrize(("raw", "iso", "ambiguous"), [
    ("14 March 2026", "2026-03-14", False), ("March 14, 2026", "2026-03-14", False),
    ("14-Mar-2026", "2026-03-14", False), ("2026-03-14", "2026-03-14", False),
    ("14/03/2026", "2026-03-14", False), ("07.07.2026", "2026-07-07", False),
    ("05/06/2026", None, True), ("03/14/2026", None, True), ("31 February 2026", None, False),
    ("sometime in spring", None, True),
])
def test_date_normalisation(raw, iso, ambiguous) -> None:
    parsed = parse_date(raw)
    assert parsed.iso == iso and parsed.ambiguous == ambiguous


@pytest.mark.parametrize(("raw", "unit", "sq_m"), [
    ("12,450 sq. m", "sq_m", 12450.0), ("12450 square metres", "sq_m", 12450.0), ("1,000 m2", "sq_m", 1000.0),
    ("86,000 sq. ft", "sq_ft", 7989.661), ("10000 sqft", "sq_ft", 929.03), ("5,000", None, None),
    ("5,000 acres", None, None),
])
def test_area_normalisation_keeps_units(raw, unit, sq_m) -> None:
    area = parse_area(raw)
    assert area.unit == unit
    assert (area.value_sq_m == pytest.approx(sq_m, abs=0.01)) if sq_m else area.value_sq_m is None


def test_name_similarity_is_conservative() -> None:
    assert text_similarity("Deccan Ridge Institute of Engineering", "DECCAN RIDGE INSTITUTE OF ENGINEERING.") == 1.0
    assert text_similarity("Society & Trust", "Society and Trust") == 1.0
    assert text_similarity("Hooghly Riverside Engineering College", "Hooghly Riverbank Polytechnic") < 0.9
    assert text_similarity("Alpha College", "Completely Different Name") < 0.6


def test_processing_rejected_for_failed_intake(client, code, app) -> None:
    from app.models.enums import DocumentStatus

    doc = upload(client, code).json()
    with app.state.session_factory() as s:
        s.get(Document, doc["id"]).status = DocumentStatus.INTAKE_FAILED
        s.commit()
    response = process(client, doc["id"])
    assert response.status_code == 409 and response.json()["error"]["code"] == "document_not_processable"
