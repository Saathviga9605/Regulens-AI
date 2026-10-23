"""Document intake, retrieval and deletion.

Duplicate policy: an upload whose SHA-256 equals an existing stored document *in the same application* is kept,
marked ``duplicate_detected`` and linked to the earliest original. Nothing is overwritten or discarded. Matches in
other applications are reported only as a count. Identical hashes mean identical bytes — not authenticity, and not
misconduct.

Deletion policy: explicit hard delete of the metadata row and the stored file. The file is first isolated in the
trash area and only discarded after the database commit succeeds (restored on failure). If the deleted document is
the original for duplicates, the earliest duplicate is promoted to original and the others are re-linked to it.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.limits import PayloadTooLarge
from app.db.types import utcnow
from app.models import Application, Document
from app.models.enums import ApplicationStatus, DocumentCategory, DocumentStatus
from app.schemas.document import DocumentRead, DuplicateReference
from app.services import workflow
from app.services.applications import get_application
from app.services.storage import DocumentStorage

logger = logging.getLogger("regulens.documents")

CHUNK_SIZE = 64 * 1024
PDF_MIME = "application/pdf"
# Declared (client-supplied) types we tolerate. This is only one signal; the file signature decides.
ACCEPTED_DECLARED_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream", ""}
INTAKE_OPEN_STATUSES = workflow.DOCUMENT_INTAKE_STATUSES
_FORBIDDEN_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"|?*]')


def _unsupported(code: str, message: str) -> AppError:
    return AppError(415, code, message, [{"loc": ["body", "file"], "msg": message}])


def intake_open(status: ApplicationStatus) -> bool:
    return workflow.document_intake_open(status)


def sanitize_filename(raw: str | None) -> str:
    """Return a display-safe base name. Never used as a filesystem path."""
    name = (raw or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."} or len(name) > 255 or _FORBIDDEN_FILENAME_CHARS.search(name):
        raise AppError(422, "invalid_filename", "The file name is empty or contains invalid characters.",
                       [{"loc": ["body", "file"], "msg": "Invalid file name."}])
    if not name.lower().endswith(".pdf") or name.lower() == ".pdf":
        raise _unsupported("unsupported_file_type", "Only PDF files with a .pdf extension are accepted.")
    return name


def check_declared_type(content_type: str | None) -> None:
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ACCEPTED_DECLARED_TYPES:
        raise _unsupported("unsupported_file_type", f"Declared content type '{declared[:60]}' is not a PDF.")


@dataclass
class ReceivedFile:
    temp_path: Path
    size: int
    sha256: str


async def receive_upload(storage: DocumentStorage, upload: UploadFile, max_bytes: int) -> ReceivedFile:
    """Stream the upload to a private temp file in chunks, hashing and validating as it goes."""
    temp = storage.new_temp_path()
    digest = hashlib.sha256()
    size = 0
    head = b""
    tail = b""
    try:
        with temp.open("wb") as out:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise PayloadTooLarge(max_bytes)
                if len(head) < 8:
                    head = (head + chunk)[:8]
                tail = (tail + chunk)[-1024:]
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise AppError(422, "empty_file", "The uploaded file is empty.",
                           [{"loc": ["body", "file"], "msg": "File is empty."}])
        if not head.startswith(b"%PDF-"):
            raise _unsupported("invalid_pdf_signature", "File content is not a PDF (missing %PDF- signature).")
        if b"%%EOF" not in tail:
            raise _unsupported("invalid_pdf_structure", "The PDF appears truncated or incomplete (no %%EOF marker).")
    except BaseException:
        DocumentStorage.discard(temp)
        raise
    return ReceivedFile(temp, size, digest.hexdigest())


def _application_for_intake(session: Session, application_code: str) -> Application:
    application = get_application(session, application_code)
    if not intake_open(application.status):
        raise ConflictError(
            "document_intake_closed",
            "Documents can only be added or removed while the application is a draft or awaiting additional evidence.",
        )
    return application


def check_intake_allowed(session: Session, application_code: str) -> None:
    _application_for_intake(session, application_code)


def _find_original(session: Session, application_id: str, sha256: str) -> Document | None:
    return session.execute(
        select(Document)
        .where(Document.application_id == application_id, Document.sha256 == sha256,
               Document.status == DocumentStatus.UPLOADED)
        .order_by(Document.uploaded_at, Document.id)
        .limit(1)
    ).scalar_one_or_none()


def store_document(
    session: Session,
    storage: DocumentStorage,
    *,
    application_code: str,
    received: ReceivedFile,
    filename: str,
    category: DocumentCategory,
    description: str | None,
) -> Document:
    """Persist metadata and move the temp file into storage atomically with the DB commit."""
    destination: Path | None = None
    try:
        application = _application_for_intake(session, application_code)
        original = _find_original(session, application.id, received.sha256)
        now = utcnow()
        document = Document(
            application_id=application.id,
            original_filename=filename,
            storage_key=storage.new_key(),
            category=category,
            mime_type=PDF_MIME,
            size_bytes=received.size,
            sha256=received.sha256,
            status=DocumentStatus.DUPLICATE_DETECTED if original else DocumentStatus.UPLOADED,
            duplicate_of_id=original.id if original else None,
            description=description,
            uploaded_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(document)
        session.flush()
        try:
            destination = storage.commit_temp(received.temp_path, document.storage_key)
        except OSError as exc:
            session.rollback()
            failed = _record_intake_failure(session, application.id, received, filename, category, description)
            logger.error("Document storage failed", extra={"error_type": type(exc).__name__})
            raise AppError(500, "document_storage_failed",
                           "The file could not be stored. The failed intake was recorded; please retry.",
                           [{"document_id": failed.id}]) from exc
        session.commit()
        return document
    except BaseException:
        session.rollback()
        DocumentStorage.discard(received.temp_path)
        DocumentStorage.discard(destination)
        raise


def _record_intake_failure(session: Session, application_id: str, received: ReceivedFile, filename: str,
                           category: DocumentCategory, description: str | None) -> Document:
    now = utcnow()
    failed = Document(application_id=application_id, original_filename=filename, storage_key=None,
                      category=category, mime_type=PDF_MIME, size_bytes=received.size, sha256=received.sha256,
                      status=DocumentStatus.INTAKE_FAILED, description=description,
                      uploaded_at=now, created_at=now, updated_at=now)
    session.add(failed)
    session.commit()
    return failed


def get_document(session: Session, document_id: str) -> Document:
    document = session.execute(
        select(Document)
        .options(joinedload(Document.application), joinedload(Document.duplicate_of))
        .where(Document.id == document_id)
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document was not found.")
    return document


def list_documents(session: Session, application_code: str, page: int, page_size: int) -> tuple[list[Document], int]:
    application = get_application(session, application_code)
    base = select(Document).where(Document.application_id == application.id)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(
        base.options(joinedload(Document.application), joinedload(Document.duplicate_of))
        .order_by(Document.uploaded_at, Document.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).scalars().all()
    return list(rows), total


def other_application_matches(session: Session, documents: list[Document]) -> dict[str, int]:
    """Per document: number of other applications with identical content (single query)."""
    if not documents:
        return {}
    hashes = {d.sha256 for d in documents}
    rows = session.execute(
        select(Document.sha256, Document.application_id)
        .where(Document.sha256.in_(hashes), Document.status != DocumentStatus.INTAKE_FAILED)
        .distinct()
    ).all()
    by_hash: dict[str, set[str]] = {}
    for sha, app_id in rows:
        by_hash.setdefault(sha, set()).add(app_id)
    return {d.id: len(by_hash.get(d.sha256, set()) - {d.application_id}) for d in documents}


def to_read(document: Document, other_matches: int, storage: DocumentStorage) -> DocumentRead:
    dup = document.duplicate_of
    return DocumentRead(
        id=document.id,
        application_code=document.application.application_code,
        original_filename=document.original_filename,
        category=document.category,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        status=document.status,
        duplicate_of=DuplicateReference(id=dup.id, original_filename=dup.original_filename, category=dup.category,
                                        uploaded_at=dup.uploaded_at) if dup else None,
        other_application_match_count=other_matches,
        content_available=storage.open_path(document.storage_key) is not None,
        description=document.description,
        uploaded_at=document.uploaded_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def content_path(session: Session, storage: DocumentStorage, document_id: str) -> tuple[Document, Path]:
    document = get_document(session, document_id)
    path = storage.open_path(document.storage_key)
    if path is None:
        raise AppError(404, "content_unavailable", "The document content is not available.")
    return document, path


def delete_document(session: Session, storage: DocumentStorage, document_id: str) -> None:
    document = get_document(session, document_id)
    if not intake_open(document.application.status):
        raise ConflictError("document_intake_closed",
                            "Documents can only be removed while the application is a draft or awaiting additional evidence.")
    dependents = session.execute(
        select(Document).where(Document.duplicate_of_id == document.id).order_by(Document.uploaded_at, Document.id)
    ).scalars().all()
    now = utcnow()
    if dependents:
        promoted, *others = dependents
        promoted.status = DocumentStatus.UPLOADED
        promoted.duplicate_of_id = None
        promoted.updated_at = now
        for other in others:
            other.duplicate_of_id = promoted.id
            other.updated_at = now

    key = document.storage_key
    isolated = storage.isolate(key) if key else None
    if key and isolated is None:
        logger.warning("Deleting document whose stored file was already missing")
    try:
        session.delete(document)
        session.commit()
    except BaseException:
        session.rollback()
        if isolated is not None and key:
            storage.restore(key, isolated)
        raise
    DocumentStorage.discard(isolated)
