"""Users/sessions, human review actions, evidence requests, audit events and in-app alerts."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, str_enum, utcnow
from app.models.enums import AuditOutcome, EvidenceRequestStatus, ReviewActionType, ReviewStatus, UserRole


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Senior cross-case review permission: granted by an administrator, never implied by the admin role.
    cross_case_reviewer: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AuthSession(Base):
    """Server-side session. Only the SHA-256 of the bearer token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship()


class FindingReviewAction(Base):
    """Append-only history of human (and carried-forward) review actions on a finding."""

    __tablename__ = "finding_review_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    finding_id: Mapped[str] = mapped_column(String(36), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False,
                                            index=True)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="RESTRICT"),
                                                nullable=False, index=True)
    action_type: Mapped[ReviewActionType] = mapped_column(str_enum(ReviewActionType, "review_action_type"),
                                                          nullable=False)
    previous_status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "previous_review_status"),
                                                          nullable=False)
    new_status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "new_review_status"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)
    actor_username: Mapped[str] = mapped_column(String(60), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="RESTRICT"),
                                                nullable=False)
    finding_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("findings.id", ondelete="SET NULL"),
                                                   nullable=True)
    finding_title: Mapped[str | None] = mapped_column(String(300), nullable=True)  # snapshot for history
    requested_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO date
    status: Mapped[EvidenceRequestStatus] = mapped_column(str_enum(EvidenceRequestStatus, "evidence_request_status"),
                                                          nullable=False, default=EvidenceRequestStatus.OPEN)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    closed_by: Mapped[str | None] = mapped_column(String(60), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    closing_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["EvidenceRequestDocument"]] = relationship(
        cascade="all, delete-orphan", order_by="EvidenceRequestDocument.linked_at", passive_deletes=True)

    __table_args__ = (Index("ix_evidence_requests_application_status", "application_id", "status"),)


class EvidenceRequestDocument(Base):
    """Explicit link between an evidence request and a document uploaded for it."""

    __tablename__ = "evidence_request_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    evidence_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("documents.id", ondelete="SET NULL"),
                                                    nullable=True)
    document_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    linked_by: Mapped[str] = mapped_column(String(60), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AuditEvent(Base):
    """Application-level append-only audit log (no update/delete API). Not a certified immutable store."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_username: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    outcome: Mapped[AuditOutcome] = mapped_column(str_enum(AuditOutcome, "audit_outcome"), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Alert(Base):
    """In-app alert for all staff (reviewers and administrators). Read state is per user."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dedup_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(20), nullable=False, default="staff")
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="RESTRICT"),
                                                nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    finding_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    __table_args__ = (Index("ix_alerts_application_created", "application_id", "created_at"),)


class AlertRead(Base):
    __tablename__ = "alert_reads"

    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
