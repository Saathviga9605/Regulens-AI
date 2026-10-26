import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT
from app.main import create_app
from app.models import Document
from app.services.storage import DocumentStorage, StorageError
from tests.conftest import authed_client, application_payload, institution_payload, make_settings


def make_pdf(text: str = "hello") -> bytes:
    return (b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n% " + text.encode()
            + b"\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def upload(client: TestClient, code: str, content: bytes = None, *, name="certificate.pdf",
           content_type="application/pdf", category="fire_safety_certificate", description=None):
    data = {"category": category}
    if description is not None:
        data["description"] = description
    return client.post(f"/api/v1/applications/{code}/documents",
                       files={"file": (name, make_pdf() if content is None else content, content_type)}, data=data)


def stored_files(storage: DocumentStorage) -> list[Path]:
    return [p for p in storage.root.rglob("*.pdf") if storage.trash not in p.parents]


def leftovers(storage: DocumentStorage) -> list[Path]:
    return list(storage.incoming.glob("*")) + list(storage.trash.glob("*"))


# --- upload ---------------------------------------------------------------------------------

def test_upload_valid_pdf(client: TestClient, code: str, storage: DocumentStorage) -> None:
    content = make_pdf("fire")
    response = upload(client, code, content, description="  Issued by synthetic fire dept  ")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["application_code"] == code
    assert body["original_filename"] == "certificate.pdf"
    assert body["category"] == "fire_safety_certificate"
    assert body["mime_type"] == "application/pdf"
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    assert body["status"] == "uploaded"
    assert body["duplicate_of"] is None
    assert body["other_application_match_count"] == 0
    assert body["content_available"] is True
    assert body["description"] == "Issued by synthetic fire dept"
    assert "storage_key" not in body and str(storage.root) not in response.text
    files = stored_files(storage)
    assert len(files) == 1 and files[0].read_bytes() == content
    assert leftovers(storage) == []


def test_upload_to_nonexistent_application(client: TestClient, storage: DocumentStorage) -> None:
    response = upload(client, "REG-EoA-2026-9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert stored_files(storage) == [] and leftovers(storage) == []


@pytest.mark.parametrize(
    ("content", "name", "content_type", "status", "error_code"),
    [
        (b"", "empty.pdf", "application/pdf", 422, "empty_file"),
        (PNG, "photo.png", "image/png", 415, "invalid_image"),  # PNG accepted since D10; this one has no IEND
        (PNG, "photo.pdf", "application/pdf", 415, "invalid_pdf_signature"),  # misleading MIME + extension
        (make_pdf(), "page.pdf", "text/html", 415, "unsupported_file_type"),  # valid PDF, hostile declared type
        (b"<html><script>alert(1)</script>%%EOF", "page.pdf", "application/pdf", 415, "invalid_pdf_signature"),
        (make_pdf()[:-7], "truncated.pdf", "application/pdf", 415, "invalid_pdf_structure"),
        (make_pdf(), "report.exe", "application/pdf", 415, "unsupported_file_type"),
        (make_pdf(), ".pdf", "application/pdf", 415, "unsupported_file_type"),
        (make_pdf(), "bad|name<1>.pdf", "application/pdf", 422, "invalid_filename"),
        (make_pdf(), "a" * 300 + ".pdf", "application/pdf", 422, "invalid_filename"),
    ],
)
def test_rejected_uploads_leave_nothing_behind(client, code, storage, content, name, content_type, status, error_code):
    response = upload(client, code, content, name=name, content_type=content_type)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == error_code
    assert stored_files(storage) == [] and leftovers(storage) == []
    assert client.get(f"/api/v1/applications/{code}/documents").json()["total"] == 0


def test_missing_or_invalid_category_rejected(client, code) -> None:
    assert upload(client, code, category="passport").status_code == 422
    response = client.post(f"/api/v1/applications/{code}/documents",
                           files={"file": ("a.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 422


def test_oversized_upload_rejected(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "small.db", max_upload_bytes=2048)
    app = create_app(settings)
    storage = app.state.document_storage
    with authed_client(app) as client:
        inst = client.post("/api/v1/institutions", json=institution_payload()).json()
        code = client.post("/api/v1/applications", json=application_payload(inst["institution_code"])).json()["application_code"]
        # Just over the limit: caught while streaming by the service.
        streamed = upload(client, code, make_pdf("x" * 3000))
        assert streamed.status_code == 413
        assert streamed.json()["error"]["code"] == "payload_too_large"
        # Far over the limit: rejected by middleware from Content-Length before the body is parsed.
        early = upload(client, code, make_pdf("x" * 200_000))
        assert early.status_code == 413
        assert early.json()["error"]["code"] == "payload_too_large"
        assert upload(client, code, make_pdf("ok")).status_code == 201
    assert len(stored_files(storage)) == 1 and leftovers(storage) == []


# --- duplicates ------------------------------------------------------------------------------

def test_exact_duplicate_is_kept_and_linked(client, code, storage) -> None:
    first = upload(client, code, make_pdf("same"), name="occupancy.pdf", category="occupancy_certificate").json()
    second = upload(client, code, make_pdf("same"), name="renamed-copy.pdf", category="other").json()
    assert first["status"] == "uploaded"
    assert second["status"] == "duplicate_detected"
    assert second["duplicate_of"] == {"id": first["id"], "original_filename": "occupancy.pdf",
                                      "category": "occupancy_certificate", "uploaded_at": first["uploaded_at"]}
    third = upload(client, code, make_pdf("same")).json()
    assert third["duplicate_of"]["id"] == first["id"]  # always linked to the original, never to a duplicate
    assert client.get(f"/api/v1/documents/{first['id']}").json() == first  # original untouched
    assert len(stored_files(storage)) == 3


def test_same_filename_different_content_is_not_duplicate(client, code) -> None:
    a = upload(client, code, make_pdf("one"), name="plan.pdf").json()
    b = upload(client, code, make_pdf("two"), name="plan.pdf").json()
    assert a["sha256"] != b["sha256"]
    assert a["status"] == b["status"] == "uploaded"


def test_multiple_documents_with_same_category(client, code) -> None:
    for i in range(3):
        assert upload(client, code, make_pdf(f"plan {i}"), category="building_plan").status_code == 201
    listing = client.get(f"/api/v1/applications/{code}/documents").json()
    assert listing["total"] == 3
    assert {d["category"] for d in listing["items"]} == {"building_plan"}
    assert [d["original_filename"] for d in listing["items"]] == ["certificate.pdf"] * 3


def test_match_in_other_application_reported_as_count_only(client, code, institution) -> None:
    other = client.post("/api/v1/applications", json=application_payload(institution["institution_code"])).json()
    upload(client, code, make_pdf("shared"), name="mine.pdf")
    theirs = upload(client, other["application_code"], make_pdf("shared"), name="theirs.pdf").json()
    assert theirs["status"] == "uploaded"  # duplicates are only flagged within one application
    assert theirs["duplicate_of"] is None
    assert theirs["other_application_match_count"] == 1
    assert "mine.pdf" not in str(theirs)
    mine = client.get(f"/api/v1/applications/{code}/documents").json()["items"][0]
    assert mine["other_application_match_count"] == 1


def test_list_is_scoped_to_application(client, code, institution) -> None:
    other = client.post("/api/v1/applications", json=application_payload(institution["institution_code"])).json()
    upload(client, code, make_pdf("a"))
    upload(client, other["application_code"], make_pdf("b"))
    items = client.get(f"/api/v1/applications/{code}/documents").json()["items"]
    assert [d["application_code"] for d in items] == [code]
    assert client.get("/api/v1/applications/REG-EoA-2026-9999/documents").status_code == 404


# --- retrieval -------------------------------------------------------------------------------

def test_metadata_persists_across_sessions(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "persist.db")
    with authed_client(create_app(settings)) as c1:
        inst = c1.post("/api/v1/institutions", json=institution_payload()).json()
        code = c1.post("/api/v1/applications", json=application_payload(inst["institution_code"])).json()["application_code"]
        doc = upload(c1, code, make_pdf("persist")).json()
    with authed_client(create_app(settings)) as c2:
        assert c2.get(f"/api/v1/documents/{doc['id']}").json() == doc
        assert c2.get(f"/api/v1/documents/{doc['id']}/content").content == make_pdf("persist")


def test_content_download_integrity_and_headers(client, code) -> None:
    content = make_pdf("download")
    doc = upload(client, code, content, name="Fire NOC – Block A.pdf").json()
    inline = client.get(f"/api/v1/documents/{doc['id']}/content")
    assert inline.status_code == 200
    assert inline.content == content
    assert hashlib.sha256(inline.content).hexdigest() == doc["sha256"]
    assert inline.headers["content-type"] == "application/pdf"
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert inline.headers["content-disposition"].startswith('inline; filename="Fire NOC _ Block A.pdf"')
    assert "filename*=UTF-8''Fire%20NOC%20%E2%80%93%20Block%20A.pdf" in inline.headers["content-disposition"]
    download = client.get(f"/api/v1/documents/{doc['id']}/content", params={"disposition": "attachment"})
    assert download.headers["content-disposition"].startswith("attachment;")
    assert client.get(f"/api/v1/documents/{doc['id']}/content", params={"disposition": "evil"}).status_code == 422


def test_missing_document_and_missing_content(client, code, storage) -> None:
    for path in ("/api/v1/documents/does-not-exist", "/api/v1/documents/does-not-exist/content"):
        response = client.get(path)
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    doc = upload(client, code).json()
    stored_files(storage)[0].unlink()
    assert client.get(f"/api/v1/documents/{doc['id']}").json()["content_available"] is False
    response = client.get(f"/api/v1/documents/{doc['id']}/content")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "content_unavailable"
    assert str(storage.root) not in response.text


# --- path traversal / storage safety ---------------------------------------------------------

def test_path_traversal_filenames_are_reduced_to_base_name(client, code, storage) -> None:
    for name in ("../../../evil.pdf", "..\\..\\windows\\evil.pdf", "/etc/evil.pdf"):
        body = upload(client, code, make_pdf(name), name=name).json()
        assert body["original_filename"] == "evil.pdf"
    for path in stored_files(storage):
        assert storage.root in path.resolve().parents
        assert "evil" not in path.name
    assert not (storage.root.parent / "evil.pdf").exists()


def test_traversal_in_document_id_routes(client) -> None:
    for path in ("/api/v1/documents/..%2F..%2Fapp%2Fmain.py/content", "/api/v1/documents/../../etc/passwd"):
        assert client.get(path).status_code == 404


def test_tampered_storage_key_is_never_resolved(client, code, app) -> None:
    doc = upload(client, code).json()
    with app.state.session_factory() as session:
        row = session.get(Document, doc["id"])
        row.storage_key = "../../../../backend/app/main"
        session.commit()
    response = client.get(f"/api/v1/documents/{doc['id']}/content")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "content_unavailable"


def test_storage_path_resolution_rejects_bad_keys(tmp_path: Path) -> None:
    storage = DocumentStorage(tmp_path / "store")
    for key in ("../x", "..", "", "ABCDEF" * 6, "0" * 31, "g" * 32):
        with pytest.raises(StorageError):
            storage.path_for(key)
    assert storage.path_for("a" * 32).parent == (tmp_path / "store" / "aa").resolve()


def test_documents_are_not_served_statically(client, code, storage) -> None:
    upload(client, code)
    stored = stored_files(storage)[0]
    for path in (f"/{stored.name}", f"/data/documents/{stored.parent.name}/{stored.name}",
                 f"/documents/{stored.name}", f"/api/v1/{stored.name}"):
        assert client.get(path).status_code == 404


def test_storage_dir_inside_frontend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path / "x.db", document_storage_dir=str(REPO_ROOT / "frontend" / "public" / "docs"))
    with pytest.raises(ValidationError):
        make_settings(tmp_path / "x.db", max_upload_bytes=10)


# --- failure handling ------------------------------------------------------------------------

def test_database_failure_cleans_up_stored_file(client, code, storage, monkeypatch) -> None:
    def failing_commit(self):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(Session, "commit", failing_commit)
    response = upload(client, code)
    monkeypatch.undo()
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert stored_files(storage) == [] and leftovers(storage) == []
    assert client.get(f"/api/v1/applications/{code}/documents").json()["total"] == 0


def test_storage_failure_records_intake_failed(client, code, storage, monkeypatch) -> None:
    def failing_commit_temp(self, temp, key):
        raise OSError("disk full")

    monkeypatch.setattr(DocumentStorage, "commit_temp", failing_commit_temp)
    response = upload(client, code)
    monkeypatch.undo()
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "document_storage_failed"
    assert "disk full" not in response.text
    items = client.get(f"/api/v1/applications/{code}/documents").json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == error["details"][0]["document_id"]
    assert items[0]["status"] == "intake_failed" and items[0]["content_available"] is False
    assert stored_files(storage) == [] and leftovers(storage) == []
    # A failed intake is not treated as an original for duplicate detection.
    assert upload(client, code).json()["status"] == "uploaded"


# --- deletion --------------------------------------------------------------------------------

def test_delete_duplicate_keeps_original(client, code, storage) -> None:
    original = upload(client, code, make_pdf("x")).json()
    duplicate = upload(client, code, make_pdf("x")).json()
    response = client.delete(f"/api/v1/documents/{duplicate['id']}")
    assert response.status_code == 204 and response.content == b""
    assert client.get(f"/api/v1/documents/{duplicate['id']}").status_code == 404
    assert client.get(f"/api/v1/documents/{original['id']}").json() == original
    assert client.get(f"/api/v1/documents/{original['id']}/content").content == make_pdf("x")
    assert len(stored_files(storage)) == 1 and leftovers(storage) == []


def test_delete_original_promotes_earliest_duplicate(client, code, storage) -> None:
    original = upload(client, code, make_pdf("x"), name="a.pdf").json()
    dup1 = upload(client, code, make_pdf("x"), name="b.pdf").json()
    dup2 = upload(client, code, make_pdf("x"), name="c.pdf").json()
    unrelated = upload(client, code, make_pdf("y"), name="d.pdf").json()
    assert client.delete(f"/api/v1/documents/{original['id']}").status_code == 204
    promoted = client.get(f"/api/v1/documents/{dup1['id']}").json()
    assert promoted["status"] == "uploaded" and promoted["duplicate_of"] is None
    relinked = client.get(f"/api/v1/documents/{dup2['id']}").json()
    assert relinked["status"] == "duplicate_detected" and relinked["duplicate_of"]["id"] == dup1["id"]
    assert client.get(f"/api/v1/documents/{unrelated['id']}").json() == unrelated
    assert len(stored_files(storage)) == 3
    # New identical upload links to the promoted original.
    assert upload(client, code, make_pdf("x")).json()["duplicate_of"]["id"] == dup1["id"]


def test_delete_with_missing_file_and_unknown_id(client, code, storage) -> None:
    doc = upload(client, code).json()
    stored_files(storage)[0].unlink()
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 204
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 404


def test_delete_rolls_back_and_restores_file_on_db_failure(client, code, storage, monkeypatch) -> None:
    doc = upload(client, code, make_pdf("keep")).json()

    def failing_commit(self):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(Session, "commit", failing_commit)
    response = client.delete(f"/api/v1/documents/{doc['id']}")
    monkeypatch.undo()
    assert response.status_code == 500
    assert client.get(f"/api/v1/documents/{doc['id']}/content").content == make_pdf("keep")
    assert leftovers(storage) == []


def test_intake_closed_outside_draft_and_awaiting_evidence(client, code) -> None:
    doc = upload(client, code).json()
    client.post(f"/api/v1/applications/{code}/status", json={"target_status": "ready_for_preliminary_scrutiny"})
    blocked = upload(client, code, make_pdf("late"))
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "document_intake_closed"
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 409
    assert client.get(f"/api/v1/applications/{code}").json()["document_intake_open"] is False
    for target in ("under_preliminary_scrutiny", "awaiting_additional_evidence"):
        client.post(f"/api/v1/applications/{code}/status", json={"target_status": target})
    assert client.get(f"/api/v1/applications/{code}").json()["document_intake_open"] is True
    assert upload(client, code, make_pdf("evidence")).status_code == 201


def test_intake_policy(client, settings) -> None:
    body = client.get("/api/v1/documents/intake-policy").json()
    assert body["max_upload_bytes"] == settings.max_upload_bytes
    assert body["accepted_content_types"] == ["application/pdf", "image/png", "image/jpeg"]
    assert len(body["categories"]) == 10 and "other" in body["categories"]
    assert {"building_license", "form_d"} <= set(body["categories"])
    assert body["intake_open_statuses"] == ["draft", "awaiting_additional_evidence"]


def test_document_rows_reference_application(client, code, app) -> None:
    upload(client, code)
    with app.state.session_factory() as session:
        doc = session.execute(select(Document)).scalar_one()
        assert doc.application.application_code == code
        assert len(doc.storage_key) == 32


def test_reset_removes_documents_and_their_files(client, code, storage, settings, app) -> None:
    from app.services import seed as seed_service

    upload(client, code, make_pdf("a"))
    upload(client, code, make_pdf("a"))  # duplicate referencing the original
    unrelated = storage.root / "keep-me.txt"
    unrelated.write_text("not a stored document")
    with app.state.session_factory() as session:
        assert seed_service.reset_data(session, settings, confirm=True) == 2
        assert seed_service.summary(session)["applications_total"] == 0
    assert stored_files(storage) == []
    assert unrelated.exists()  # only files referenced by deleted rows are removed
