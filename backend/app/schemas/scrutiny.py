"""Schemas for document processing, scrutiny rules/runs/findings and simulated issuer verification."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    Confidence,
    DocumentCategory,
    FieldStatus,
    FindingKind,
    PageExtractionMethod,
    PageStatus,
    ProcessingStatus,
    ReviewStatus,
    RuleOutcome,
    RuleType,
    RunStatus,
    Severity,
    SourceVerificationStatus,
    VerificationOutcome,
)
from app.schemas.common import PartialUpdateModel, StrictInputModel

# --- Processing ------------------------------------------------------------------------------------


class ProcessingSummary(BaseModel):
    status: ProcessingStatus
    pipeline_version: str
    is_current: bool
    predicted_category: DocumentCategory | None
    classification_confidence: str
    warning_count: int
    finished_at: datetime


class ExtractedFieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    field_name: str
    raw_value: str | None
    normalized_value: dict | None
    page_number: int | None
    evidence_quote: str | None
    method: str
    confidence: Confidence
    status: FieldStatus
    warnings: list[str]
    candidates: list[dict]


class ClassificationRead(BaseModel):
    predicted_category: DocumentCategory | None
    selected_category: DocumentCategory
    confidence: str = Field(description="high | medium | uncertain — heuristic, not a probability")
    score: float = Field(description="Share of total signal weight held by the top category (0–1)")
    signals: list[dict]
    alternatives: list[dict]
    agrees_with_selected: bool | None


class PageSummary(BaseModel):
    page_number: int
    method: PageExtractionMethod
    status: PageStatus
    char_count: int
    warnings: list[str]


class ProcessingRead(BaseModel):
    document_id: str
    application_code: str
    status: ProcessingStatus
    failure_code: str | None
    failure_reason: str | None
    pipeline_version: str
    is_current: bool
    reused_from_cache: bool
    ocr_available: bool
    page_count: int
    pages_processed: int
    warnings: list[str]
    classification: ClassificationRead
    pages: list[PageSummary]
    fields: list[ExtractedFieldRead]
    started_at: datetime
    finished_at: datetime


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    method: PageExtractionMethod
    status: PageStatus
    char_count: int
    text: str
    warnings: list[str]


# --- Rules -----------------------------------------------------------------------------------------


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    title: str
    description: str
    rule_type: RuleType
    parameters: dict
    severity: Severity
    enabled: bool
    source: str
    source_reference: str | None
    source_verification_status: SourceVerificationStatus
    is_demo_only: bool
    provenance: str
    registry_managed: bool
    retired: bool
    effective_from: str | None
    effective_to: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class RuleCreate(StrictInputModel):
    rule_id: str = Field(pattern=r"^[A-Z]{2,6}-\d{3}$")
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=2000)
    rule_type: RuleType
    parameters: dict = Field(default_factory=dict)
    severity: Severity
    enabled: bool = True
    source: str = Field(min_length=3, max_length=300)
    source_reference: str | None = Field(default=None, max_length=300)
    source_verification_status: SourceVerificationStatus = SourceVerificationStatus.UNVERIFIED
    is_demo_only: bool = True


class RuleUpdate(PartialUpdateModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=2000)
    parameters: dict | None = None
    severity: Severity | None = None
    enabled: bool | None = None
    source: str | None = Field(default=None, min_length=3, max_length=300)
    source_reference: str | None = Field(default=None, max_length=300)
    source_verification_status: SourceVerificationStatus | None = None
    is_demo_only: bool | None = None


# --- Runs and findings -----------------------------------------------------------------------------


class RunSummaryRead(BaseModel):
    id: str
    application_code: str
    run_number: int
    status: RunStatus
    scrutiny_date: str | None
    scrutiny_date_source: str
    rule_set_version: str
    ruleset_profile: str
    ruleset_profile_version: str
    summary: dict
    warnings: list[str]
    failure_reason: str | None
    started_at: datetime
    finished_at: datetime | None


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    rule_version: int
    subject_key: str
    outcome: RuleOutcome
    severity: Severity
    explanation: str
    document_ids: list[str]
    field_ids: list[str]
    evidence: list[dict]
    compared_values: list[dict]
    missing_evidence: str | None
    human_review_recommended: bool


class RunRead(RunSummaryRead):
    rule_snapshot: list[dict]
    documents_considered: list[dict]
    evaluations: list[EvaluationRead]


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    finding_key: str
    kind: FindingKind
    finding_type: str
    title: str
    severity: Severity
    outcome: RuleOutcome
    explanation: str
    uncertainty: str | None
    rule_id: str | None
    rule_version: int | None
    detector: str | None
    document_ids: list[str]
    field_ids: list[str]
    evidence: list[dict]
    compared_values: list[dict]
    missing_evidence: str | None
    human_review_recommended: bool
    review_status: ReviewStatus
    review_note: str | None
    reviewed_at: datetime | None
    review_version: int
    allowed_actions: list[str] = Field(default_factory=list, description="Review actions valid in the current state")
    created_at: datetime


class FindingDetail(FindingRead):
    application_code: str
    run_number: int
    rule: dict | None = Field(description="Rule as snapshotted for this run (title, source, demo-only flag)")


# --- Simulated issuer verification ------------------------------------------------------------------


class VerificationAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str | None
    document_filename: str
    adapter: str
    method: str
    simulated: bool
    simulation_label: str | None
    outcome: VerificationOutcome
    explanation: str
    fields_compared: list[dict]
    reference_code: str | None
    created_at: datetime
