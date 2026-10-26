import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_app_settings, get_current_actor, get_db, get_pagination, get_storage
from app.core.context import Actor
from app.core.errors import ConflictError
from app.services import review
from app.services.applications import get_application
from app.core.config import Settings
from app.models.enums import DocumentCategory
from app.schemas.common import Page
from app.schemas.document import DocumentRead, IntakePolicy
from app.services import documents as service
from app.services.storage import DocumentStorage

router = APIRouter(tags=["documents"])


@router.get("/documents/intake-policy", response_model=IntakePolicy)
def intake_policy(settings: Settings = Depends(get_app_settings)) -> IntakePolicy:
    return IntakePolicy(
        max_upload_bytes=settings.max_upload_bytes,
        accepted_content_types=list(service.ACCEPTED_MIME),
        accepted_extensions=list(service.EXTENSIONS),
        categories=list(DocumentCategory),
        intake_open_statuses=list(service.INTAKE_OPEN_STATUSES),
    )


@router.post("/applications/{application_code}/documents", response_model=DocumentRead, status_code=201)
async def upload_document(
    application_code: str,
    file: UploadFile = File(..., description="PDF, PNG or JPEG file"),
    category: DocumentCategory = Form(...),
    description: str | None = Form(None, max_length=500),
    evidence_request_id: str | None = Form(None, max_length=36,
                                           description="Optional: explicitly link the upload to this open evidence request"),
    actor: Actor = Depends(get_current_actor),
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_storage),
    settings: Settings = Depends(get_app_settings),
) -> DocumentRead:
    # Cheap checks first: application exists and accepts documents, name and declared type are plausible.
    await run_in_threadpool(service.check_intake_allowed, db, application_code)
    evidence_request = None
    if evidence_request_id:
        application = await run_in_threadpool(get_application, db, application_code)
        evidence_request = await run_in_threadpool(review.scoped_request, db, application, evidence_request_id)
        if evidence_request.status.value != "open":
            raise ConflictError("evidence_request_closed", "The selected evidence request is not open.")
    filename = service.sanitize_filename(file.filename)
    service.check_declared_type(file.content_type)
    received = await service.receive_upload(storage, file, settings.max_upload_bytes, filename)
    document = await run_in_threadpool(
        lambda: service.store_document(
            db, storage, application_code=application_code, received=received, filename=filename,
            category=category, description=(description or "").strip() or None,
        )
    )
    if evidence_request is not None:
        await run_in_threadpool(lambda: review.link_document(db, document.application, evidence_request, document, actor))
    return await run_in_threadpool(
        lambda: service.to_read(document, service.other_application_matches(db, [document])[document.id], storage)
    )


@router.get("/applications/{application_code}/documents", response_model=Page[DocumentRead])
def list_documents(
    application_code: str,
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_storage),
) -> Page[DocumentRead]:
    rows, total = service.list_documents(db, application_code, pagination.page, pagination.page_size)
    matches = service.other_application_matches(db, rows)
    summaries = service.processing_summaries(db, rows)
    return Page.build([service.to_read(d, matches[d.id], storage, summaries.get(d.id)) for d in rows], total,
                      pagination.page, pagination.page_size)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: str, db: Session = Depends(get_db),
                 storage: DocumentStorage = Depends(get_storage)) -> DocumentRead:
    document = service.get_document(db, document_id)
    return service.to_read(document, service.other_application_matches(db, [document])[document.id], storage,
                           service.processing_summaries(db, [document]).get(document.id))


def _content_disposition(kind: str, filename: str) -> str:
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", filename) or "document.pdf"
    return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.get("/documents/{document_id}/content", response_class=FileResponse,
            responses={200: {"content": {"application/pdf": {}}}})
def get_document_content(
    document_id: str,
    disposition: Literal["inline", "attachment"] = Query("inline"),
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_storage),
) -> FileResponse:
    document, path = service.content_path(db, storage, document_id)
    return FileResponse(
        path,
        media_type=document.mime_type if document.mime_type in service.ACCEPTED_MIME else service.PDF_MIME,
        headers={
            "Content-Disposition": _content_disposition(disposition, document.original_filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/documents/{document_id}", status_code=204, response_class=Response)
def delete_document(document_id: str, db: Session = Depends(get_db),
                    storage: DocumentStorage = Depends(get_storage)) -> Response:
    service.delete_document(db, storage, document_id)
    return Response(status_code=204)
