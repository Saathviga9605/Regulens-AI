"""Document processing results: page text, classification and evidence-grounded fields.

One ``DocumentProcessing`` row per document holds the latest result for (sha256, pipeline_version).
Rows cascade-delete with their document at the database level.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, str_enum, utcnow
from app.models.document import Document
from app.models.enums import (
    Confidence,
    DocumentCategory,
    FieldStatus,
    PageExtractionMethod,
    PageStatus,
    ProcessingStatus,
)


class DocumentProcessing(Base):
    __tablename__ = "document_processing"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pipeline_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[ProcessingStatus] = mapped_column(str_enum(ProcessingStatus, "processing_status"), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_available: Mapped[bool] = mapped_column(nullable=False, default=False)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    predicted_category: Mapped[DocumentCategory | None] = mapped_column(
        str_enum(DocumentCategory, "predicted_category"), nullable=True
    )
    classification_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    classification_confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="uncertain")
    classification_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    classification_alternatives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reused_from_cache: Mapped[bool] = mapped_column(nullable=False, default=False)
    pdf_properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    document: Mapped[Document] = relationship()
    pages: Mapped[list["DocumentPage"]] = relationship(
        cascade="all, delete-orphan", order_by="DocumentPage.page_number", passive_deletes=True
    )
    fields: Mapped[list["ExtractedField"]] = relationship(
        cascade="all, delete-orphan", order_by="ExtractedField.position", passive_deletes=True
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_processing.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    method: Mapped[PageExtractionMethod] = mapped_column(str_enum(PageExtractionMethod, "page_method"), nullable=False)
    status: Mapped[PageStatus] = mapped_column(str_enum(PageStatus, "page_status"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Evidence coordinates (normalised [x0, y0, x1, y1], origin top-left of the displayed page) per text line.
    lines: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ocr_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # engine score, not calibrated
    rotation_degrees: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("processing_id", "page_number", name="uq_page_per_processing"),)


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    processing_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_processing.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    field_name: Mapped[str] = mapped_column(String(60), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[Confidence] = mapped_column(str_enum(Confidence, "field_confidence"), nullable=False)
    status: Mapped[FieldStatus] = mapped_column(str_enum(FieldStatus, "field_status"), nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # text_layer / ocr
    evidence_box: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # separate from extraction confidence

    __table_args__ = (Index("ix_extracted_fields_document_field", "document_id", "field_name"),)
