"""Document processing orchestration: text/OCR → classification → field extraction → persistence.

Caching: results are keyed by (document sha256, PIPELINE_VERSION). A document is reprocessed when it has no
result, its stored checksum/pipeline version differ, or ``force`` is set. A completed result for identical
content (same sha256 and pipeline version) on another document is copied instead of re-extracted.
The selected upload category is never changed; disagreements become warnings for review.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.errors import AppError
from app.db.types import utcnow
from app.models import Document, DocumentPage, DocumentProcessing, ExtractedField
from app.models.enums import DocumentCategory, DocumentStatus, PageExtractionMethod, ProcessingStatus
from app.services import classification, extraction, pdf_text
from app.services import alerts, audit
from app.services.storage import DocumentStorage

logger = logging.getLogger("regulens.processing")

# Bump the leading component whenever text extraction/OCR behaviour changes; cached results then refresh.
PIPELINE_VERSION = f"p1+{classification.CLASSIFIER_VERSION}+{extraction.EXTRACTOR_VERSION}"
CONFIDENT = ("high", "medium")


def get_processing(session: Session, document_id: str) -> DocumentProcessing | None:
    return session.execute(
        select(DocumentProcessing)
        .options(selectinload(DocumentProcessing.fields), selectinload(DocumentProcessing.pages))
        .where(DocumentProcessing.document_id == document_id)
    ).scalar_one_or_none()


def is_current(processing: DocumentProcessing | None, document: Document) -> bool:
    return (processing is not None and processing.sha256 == document.sha256
            and processing.pipeline_version == PIPELINE_VERSION)


def _category_warnings(document: Document, cls: classification.Classification) -> list[str]:
    predicted = cls.predicted_category
    if cls.confidence == "uncertain":
        return ["Document type could not be determined confidently from the text; review the selected category."]
    if predicted and predicted != document.category:
        if document.category == DocumentCategory.OTHER:
            return [f"Uploaded as 'other'; text signals suggest '{predicted.value}' ({cls.confidence} confidence). "
                    "The selected category was kept."]
        return [f"Selected category '{document.category.value}' differs from the predicted '{predicted.value}' "
                f"({cls.confidence} confidence). The selected category was kept; please review."]
    return []


def process_document(session: Session, storage: DocumentStorage, settings: Settings, ocr: pdf_text.OcrEngine | None,
                     document: Document, *, force: bool = False) -> tuple[DocumentProcessing, bool]:
    """Return (processing, reused). Commits."""
    if document.status == DocumentStatus.INTAKE_FAILED:
        raise AppError(409, "document_not_processable", "This document failed intake and has no stored content.")
    existing = get_processing(session, document.id)
    if not force and is_current(existing, document):
        return existing, True

    started = utcnow()
    cached = None if force else session.execute(
        select(DocumentProcessing)
        .options(selectinload(DocumentProcessing.fields), selectinload(DocumentProcessing.pages))
        .where(DocumentProcessing.sha256 == document.sha256,
               DocumentProcessing.pipeline_version == PIPELINE_VERSION,
               DocumentProcessing.status == ProcessingStatus.COMPLETED,
               DocumentProcessing.document_id != document.id)
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None:
        session.delete(existing)
        session.flush()

    if cached is not None:
        result = _copy_from(cached, document, started)
    else:
        result = _run_pipeline(storage, settings, ocr, document, started)
    session.add(result)
    audit.record(session, "document.processed", "document", document.id, application_id=document.application_id,
                 details={"status": result.status.value, "failure_code": result.failure_code,
                          "pipeline_version": PIPELINE_VERSION, "reused_from_cache": cached is not None,
                          "forced": force})
    if result.status == ProcessingStatus.FAILED:
        alerts.raise_alert(session, dedup_key=f"processing_failed:{document.id}:{document.sha256[:16]}:{PIPELINE_VERSION}",
                           application_id=document.application_id, event_type="processing_failed", severity="medium",
                           document_id=document.id, title="Document could not be read",
                           message=f"'{document.original_filename}': {result.failure_reason or 'processing failed'}")
    session.commit()
    return get_processing(session, document.id), cached is not None


def _copy_from(cached: DocumentProcessing, document: Document, started) -> DocumentProcessing:
    cls = classification.Classification(cached.predicted_category, cached.classification_score,
                                        cached.classification_confidence)
    processing = DocumentProcessing(
        document_id=document.id, sha256=document.sha256, pipeline_version=PIPELINE_VERSION, status=cached.status,
        failure_code=cached.failure_code, failure_reason=cached.failure_reason, page_count=cached.page_count,
        pages_processed=cached.pages_processed, ocr_available=cached.ocr_available,
        warnings=[w for w in cached.warnings if not w.startswith("Selected category") and not w.startswith("Uploaded as")]
        + _category_warnings(document, cls),
        predicted_category=cached.predicted_category, classification_score=cached.classification_score,
        classification_confidence=cached.classification_confidence,
        classification_signals=cached.classification_signals,
        classification_alternatives=cached.classification_alternatives, reused_from_cache=True,
        pdf_properties=cached.pdf_properties, started_at=started, finished_at=utcnow(),
    )
    processing.pages = [DocumentPage(page_number=p.page_number, method=p.method, status=p.status, text=p.text,
                                     char_count=p.char_count, warnings=p.warnings, lines=p.lines,
                                     ocr_engine=p.ocr_engine, ocr_confidence=p.ocr_confidence,
                                     rotation_degrees=p.rotation_degrees) for p in cached.pages]
    processing.fields = [ExtractedField(document_id=document.id, position=f.position, field_name=f.field_name,
                                        raw_value=f.raw_value, normalized_value=f.normalized_value,
                                        page_number=f.page_number, evidence_quote=f.evidence_quote, method=f.method,
                                        confidence=f.confidence, status=f.status, warnings=f.warnings,
                                        candidates=f.candidates, evidence_source=f.evidence_source,
                                        evidence_box=f.evidence_box, ocr_confidence=f.ocr_confidence)
                         for f in cached.fields]
    return processing


def _run_pipeline(storage: DocumentStorage, settings: Settings, ocr, document: Document, started) -> DocumentProcessing:
    path = storage.open_path(document.storage_key)
    if path is None:
        text = pdf_text.TextExtractionResult(status=ProcessingStatus.FAILED, failure_code="content_unavailable",
                                             failure_reason="The stored file is not available.",
                                             ocr_available=bool(ocr and ocr.available))
    else:
        text = pdf_text.extract_text(path, ocr, min_chars=settings.min_page_text_chars,
                                     max_pages=settings.max_processing_pages, dpi=settings.ocr_dpi)

    processing = DocumentProcessing(
        document_id=document.id, sha256=document.sha256, pipeline_version=PIPELINE_VERSION, status=text.status,
        failure_code=text.failure_code, failure_reason=text.failure_reason, page_count=text.page_count,
        pages_processed=len(text.pages), ocr_available=text.ocr_available, warnings=list(text.warnings),
        pdf_properties=text.pdf_properties, started_at=started,
    )
    processing.pages = [DocumentPage(page_number=p.page_number, method=p.method, status=p.status, text=p.text,
                                     char_count=pdf_text.non_ws_len(p.text), warnings=p.warnings, lines=p.lines,
                                     ocr_engine=p.ocr_engine, ocr_confidence=p.ocr_confidence,
                                     rotation_degrees=p.rotation_degrees) for p in text.pages]

    readable = [p for p in text.pages if p.status.value == "ok"]
    cls = classification.classify([p.text for p in readable])
    processing.predicted_category = cls.predicted_category
    processing.classification_score = cls.score
    processing.classification_confidence = cls.confidence
    processing.classification_signals = cls.signals
    processing.classification_alternatives = cls.alternatives
    if text.status != ProcessingStatus.FAILED:
        processing.warnings = processing.warnings + _category_warnings(document, cls)
        categories = {document.category}
        if cls.predicted_category:
            categories.add(cls.predicted_category)
        inputs = [extraction.PageInput(p.page_number, p.text, p.method, p.lines) for p in readable]
        fields = extraction.extract_fields(inputs, categories)
        processing.fields = [
            ExtractedField(document_id=document.id, position=i, field_name=f.field_name, raw_value=f.raw_value,
                           normalized_value=f.normalized_value, page_number=f.page_number,
                           evidence_quote=f.evidence_quote, method=f.method, confidence=f.confidence,
                           status=f.status, warnings=f.warnings, candidates=f.candidates,
                           evidence_source=f.evidence_source, evidence_box=f.evidence_box,
                           ocr_confidence=f.ocr_confidence)
            for i, f in enumerate(fields)
        ]
        if any(p.method == PageExtractionMethod.OCR for p in readable) and \
                processing.status == ProcessingStatus.COMPLETED:
            processing.status = ProcessingStatus.COMPLETED_WITH_WARNINGS
    processing.finished_at = utcnow()
    return processing
