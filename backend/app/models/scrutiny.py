"""Preliminary scrutiny: configurable rules, runs, evaluations, findings and simulated issuer verification.

Findings and evaluations keep JSON references (ids + filename/page/quote snapshots) to documents and
fields rather than foreign keys, so run history survives later document deletion or reprocessing.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, str_enum, utcnow
from app.models.enums import (
    DocumentCategory,
    FindingKind,
    ReferenceAvailability,
    ReviewStatus,
    RuleOutcome,
    RuleType,
    RunStatus,
    Severity,
    IssuerSourceStatus,
    SourceType,
    SourceVerificationStatus,
    VerificationOutcome,
)


class ScrutinyRule(Base):
    __tablename__ = "scrutiny_rules"

    rule_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(str_enum(RuleType, "rule_type"), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "rule_severity"), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_verification_status: Mapped[SourceVerificationStatus] = mapped_column(
        str_enum(SourceVerificationStatus, "source_verification_status"), nullable=False
    )
    is_demo_only: Mapped[bool] = mapped_column(nullable=False, default=True)
    provenance: Mapped[str] = mapped_column(String(20), nullable=False, default="demo")
    registry_managed: Mapped[bool] = mapped_column(nullable=False, default=False)
    retired: Mapped[bool] = mapped_column(nullable=False, default=False)
    effective_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ScrutinyRun(Base):
    __tablename__ = "scrutiny_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus, "run_status"), nullable=False)
    scrutiny_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO reference date
    scrutiny_date_source: Mapped[str] = mapped_column(String(40), nullable=False, default="system_date_legacy")
    rule_set_version: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    documents_considered: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    evaluations: Mapped[list["RuleEvaluation"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="RuleEvaluation.position"
    )

    __table_args__ = (
        UniqueConstraint("application_id", "run_number", name="uq_run_number_per_application"),
        Index("ix_scrutiny_runs_application_started", "application_id", "started_at"),
    )


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scrutiny_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_id: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_key: Mapped[str] = mapped_column(String(120), nullable=False)
    outcome: Mapped[RuleOutcome] = mapped_column(str_enum(RuleOutcome, "rule_outcome"), nullable=False)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "evaluation_severity"), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    field_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    compared_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_review_recommended: Mapped[bool] = mapped_column(nullable=False, default=False)

    __table_args__ = (UniqueConstraint("run_id", "rule_id", "subject_key", name="uq_evaluation_subject"),)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("scrutiny_runs.id", ondelete="CASCADE"), nullable=False)
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rule_evaluations.id", ondelete="CASCADE"), nullable=True
    )
    # Stable across runs for the same rule/detector and subject, so reruns can be compared.
    finding_key: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[FindingKind] = mapped_column(str_enum(FindingKind, "finding_kind"), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "finding_severity"), nullable=False)
    outcome: Mapped[RuleOutcome] = mapped_column(str_enum(RuleOutcome, "finding_outcome"), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detector: Mapped[str | None] = mapped_column(String(60), nullable=True)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    field_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    compared_values: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_review_recommended: Mapped[bool] = mapped_column(nullable=False, default=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        str_enum(ReviewStatus, "review_status"), nullable=False, default=ReviewStatus.NOT_REVIEWED
    )
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Optimistic concurrency for review actions: clients send the version they saw.
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("run_id", "finding_key", name="uq_finding_key_per_run"),
        Index("ix_findings_application_run", "application_id", "run_id"),
    )


class IssuerReferenceRecord(Base):
    """SYNTHETIC reference data for the mock issuer adapter. Never real issuer data."""

    __tablename__ = "issuer_reference_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    document_category: Mapped[DocumentCategory] = mapped_column(
        str_enum(DocumentCategory, "reference_category"), nullable=False
    )
    issuing_authority: Mapped[str] = mapped_column(String(200), nullable=False)
    certificate_number: Mapped[str] = mapped_column(String(100), nullable=False)
    certificate_number_normalized: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    institution_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    valid_until: Mapped[str | None] = mapped_column(String(10), nullable=True)
    availability: Mapped[ReferenceAvailability] = mapped_column(
        str_enum(ReferenceAvailability, "reference_availability"), nullable=False
    )
    seed_key: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False
    )
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter: Mapped[str] = mapped_column(String(60), nullable=False)
    method: Mapped[str] = mapped_column(String(60), nullable=False)
    simulated: Mapped[bool] = mapped_column(nullable=False)
    outcome: Mapped[VerificationOutcome] = mapped_column(
        str_enum(VerificationOutcome, "verification_outcome"), nullable=False
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    fields_compared: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reference_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Source-verification dimension (migration 0009), derived from the adapter outcome by services/source_status.py.
    source_status: Mapped[IssuerSourceStatus] = mapped_column(
        str_enum(IssuerSourceStatus, "issuer_source_status"), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(str_enum(SourceType, "source_type"), nullable=False)
    # Set only for manual records: the reviewer who recorded the result of their own check (migration 0010).
    recorded_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_verification_attempts_application", "application_id", "created_at"),)
