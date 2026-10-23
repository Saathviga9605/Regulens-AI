from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApplicationStatus,
    AuditOutcome,
    EvidenceRequestStatus,
    ReviewActionType,
    ReviewStatus,
    UserRole,
)
from app.schemas.common import PartialUpdateModel, StrictInputModel

# --- Auth & users ---------------------------------------------------------------------------------


class LoginRequest(StrictInputModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead


class UserCreate(StrictInputModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9._-]{3,60}$")
    display_name: str = Field(min_length=2, max_length=120)
    role: UserRole
    password: str = Field(min_length=10, max_length=200)


class UserUpdate(PartialUpdateModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


# --- Review actions -------------------------------------------------------------------------------


class EvidenceRef(StrictInputModel):
    document_id: str = Field(max_length=36)
    page_number: int | None = Field(default=None, ge=1, le=10000)


class ReviewActionRequest(StrictInputModel):
    action: ReviewActionType
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    requested_evidence: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None


class ReviewActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    finding_id: str
    action_type: ReviewActionType
    previous_status: ReviewStatus
    new_status: ReviewStatus
    actor_username: str
    note: str | None
    evidence_refs: list[dict]
    evidence_request_id: str | None
    created_at: datetime


# --- Evidence requests ----------------------------------------------------------------------------


class EvidenceRequestCreate(StrictInputModel):
    requested_evidence: str = Field(min_length=5, max_length=2000)
    reason: str = Field(min_length=10, max_length=2000)
    due_date: date | None = None
    finding_id: str | None = Field(default=None, max_length=36)


class EvidenceLink(StrictInputModel):
    document_id: str = Field(max_length=36)


class EvidenceClose(StrictInputModel):
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)


class LinkedDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str | None
    document_filename: str
    linked_by: str
    linked_at: datetime


class EvidenceRequestRead(BaseModel):
    id: str
    application_code: str
    finding_id: str | None
    finding_title: str | None
    requested_evidence: str
    reason: str
    due_date: str | None
    status: EvidenceRequestStatus
    is_overdue: bool
    version: int
    created_by: str
    created_at: datetime
    closed_by: str | None
    closed_at: datetime | None
    closing_note: str | None
    documents: list[LinkedDocumentRead]


# --- Audit & alerts --------------------------------------------------------------------------------


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    actor_username: str
    action: str
    resource_type: str
    resource_id: str | None
    application_id: str | None
    outcome: AuditOutcome
    request_id: str | None
    details: dict


class AlertRead(BaseModel):
    id: str
    application_code: str
    event_type: str
    severity: str
    title: str
    message: str
    finding_id: str | None
    evidence_request_id: str | None
    document_id: str | None
    created_at: datetime
    read: bool


class AlertPage(BaseModel):
    items: list[AlertRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    unread_count: int


class MarkRead(StrictInputModel):
    alert_ids: list[str] = Field(min_length=1, max_length=200)


# --- Queue -----------------------------------------------------------------------------------------


class QueueItem(BaseModel):
    application_code: str
    institution_name: str
    institution_code: str
    application_type: str
    academic_year: str
    status: ApplicationStatus
    latest_run_number: int | None
    latest_run_status: str | None
    latest_run_finished_at: datetime | None
    unresolved_by_severity: dict
    unresolved_total: int
    findings_total: int
    open_evidence_requests: int
    overdue_evidence_requests: int
    review_state: str


class QueuePage(BaseModel):
    items: list[QueueItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    counts: dict


# --- Copilot ---------------------------------------------------------------------------------------


class CopilotQuestion(StrictInputModel):
    question: str = Field(min_length=2, max_length=500)
    finding_id: str | None = Field(default=None, max_length=36)


class CopilotSource(BaseModel):
    id: str
    kind: str
    label: str
    finding_id: str | None
    document_id: str | None
    document_filename: str | None
    page_number: int | None
    quote: str | None


class CopilotAnswer(BaseModel):
    intent: str
    lines: list[str]
    sources: list[CopilotSource]
    grounded: bool
    limitations: list[str]
    disclaimer: str
    suggestions: list[str]
