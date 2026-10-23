from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ApplicationStatus, DocumentCategory, DocumentStatus


class DuplicateReference(BaseModel):
    """Earlier document in the same application with identical content (SHA-256)."""

    id: str
    original_filename: str
    category: DocumentCategory
    uploaded_at: datetime


class DocumentRead(BaseModel):
    id: str
    application_code: str
    original_filename: str
    category: DocumentCategory
    mime_type: str
    size_bytes: int
    sha256: str
    status: DocumentStatus
    duplicate_of: DuplicateReference | None
    # Number of *other* applications holding identical content. No details are exposed.
    other_application_match_count: int
    content_available: bool
    description: str | None
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime


class IntakePolicy(BaseModel):
    max_upload_bytes: int
    accepted_content_types: list[str]
    accepted_extensions: list[str]
    categories: list[DocumentCategory]
    intake_open_statuses: list[ApplicationStatus]
