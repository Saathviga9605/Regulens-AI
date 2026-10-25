"""Schemas for cross-case reuse detection. Restricted views never carry linked-case identities or evidence."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PairActionType, PairReviewStatus, ReuseOutcome, ReuseScanStatus
from app.schemas.common import StrictInputModel


class ScanRunRead(BaseModel):
    """Counts only: safe for any reviewer of the subject application."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ReuseScanStatus
    pipeline_version: str
    config_version: str
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None
    documents_scanned: int
    comparisons: int
    candidates: int
    pairs_created: int
    pairs_reused: int
    outcome_counts: dict[str, int]
    failure_reason: str | None


class LocalDocumentRef(BaseModel):
    document_id: str | None
    filename: str | None


class LinkedSummary(BaseModel):
    application_code: str | None
    institution_name: str | None
    filename: str | None


class CaseAlert(BaseModel):
    pair_id: str
    outcome: ReuseOutcome
    review_status: PairReviewStatus
    detected_at: datetime
    local_document: LocalDocumentRef
    restricted: bool
    linked: LinkedSummary | None = None  # only for cross-case reviewers


class CaseAlertList(BaseModel):
    items: list[CaseAlert]
    can_view_details: bool
    latest_scan: ScanRunRead | None
    notice: str


class PairSide(BaseModel):
    document_id: str | None
    document_available: bool
    filename: str | None
    category: str | None
    application_code: str | None
    institution_name: str | None
    page_count: int | None
    sha256: str


class PairSummary(BaseModel):
    id: str
    outcome: ReuseOutcome
    outcome_meaning: str
    review_status: PairReviewStatus
    review_version: int
    candidate_methods: list[str]
    candidate_score: float | None
    pipeline_version: str
    config_version: str
    created_at: datetime
    updated_at: datetime
    a: PairSide
    b: PairSide


class EvidenceRead(BaseModel):
    exact: dict
    text: dict
    visual: dict
    geometric: dict | None
    fields: dict
    matched_pages: list[dict]
    reasons: list[str]
    uncertainties: list[str]
    stage_status: dict
    config: dict
    latency_ms: float
    created_at: datetime


class PairActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action_type: PairActionType
    previous_status: PairReviewStatus
    new_status: PairReviewStatus
    actor_username: str
    note: str | None
    created_at: datetime


class PairDetail(PairSummary):
    evidence: EvidenceRead
    actions: list[PairActionRead]
    notice: str
    limitations: list[str]


class PairActionRequest(StrictInputModel):
    action: PairActionType
    note: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    created_by: str
    eval_version: str
    dataset_version: str
    dataset_digest: str
    config_version: str
    pipeline_version: str
    duration_ms: float


class EvaluationDetail(EvaluationSummary):
    results: dict
