"""Cross-case document reuse: cached document descriptors, scan runs, case pairs, match evidence, reviewer
dispositions and stored evaluations.

A ``CasePair`` is keyed by ``input_key`` = hash(document ids, SHA-256s, pipeline version, config version), so a
rerun on unchanged inputs and configuration finds the existing pair instead of creating a duplicate, while a
changed document, algorithm or threshold configuration produces a new, separately stored evaluation. Evidence is
written once per pair and never rewritten; reviewer actions are an append-only history beside it.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, str_enum, utcnow
from app.models.enums import PairActionType, PairReviewStatus, ReuseOutcome, ReuseScanStatus


def _uuid() -> str:
    return str(uuid.uuid4())


class DocumentFingerprint(Base):
    """Cached per-document reuse descriptors (normalised-text fingerprint, page pHashes) for one feature version."""

    __tablename__ = "document_fingerprints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(120), nullable=False)
    text_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    text_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("document_id", "feature_version", name="uq_fingerprint_document_version"),)


class ReuseScanRun(Base):
    __tablename__ = "reuse_scan_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="RESTRICT"),
                                                nullable=False)
    status: Mapped[ReuseScanStatus] = mapped_column(str_enum(ReuseScanStatus, "reuse_scan_status"), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(120), nullable=False)
    config_version: Mapped[str] = mapped_column(String(40), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    triggered_by: Mapped[str] = mapped_column(String(60), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    documents_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comparisons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pairs_reused: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    outcome_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (Index("ix_reuse_scan_runs_application_started", "application_id", "started_at"),)


class CasePair(Base):
    __tablename__ = "case_pairs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    input_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Documents may later be deleted; the pair, its evidence and its snapshot remain for the record.
    document_a_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("documents.id", ondelete="SET NULL"),
                                                      nullable=True)
    document_b_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("documents.id", ondelete="SET NULL"),
                                                      nullable=True)
    application_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="RESTRICT"),
                                                  nullable=False, index=True)
    application_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="RESTRICT"),
                                                  nullable=False, index=True)
    sha256_a: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256_b: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_methods: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    outcome: Mapped[ReuseOutcome] = mapped_column(str_enum(ReuseOutcome, "reuse_outcome"), nullable=False, index=True)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(120), nullable=False)
    config_version: Mapped[str] = mapped_column(String(40), nullable=False)
    review_status: Mapped[PairReviewStatus] = mapped_column(str_enum(PairReviewStatus, "pair_review_status"),
                                                            nullable=False, default=PairReviewStatus.NOT_REVIEWED)
    review_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("reuse_scan_runs.id", ondelete="SET NULL"),
                                                     nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("reuse_scan_runs.id", ondelete="SET NULL"),
                                                    nullable=True)
    # Ground truth exists only for isolated evaluation fixtures, never inferred for production pairs.
    is_evaluation_fixture: Mapped[bool] = mapped_column(nullable=False, default=False)
    ground_truth_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    evidence: Mapped["MatchEvidence"] = relationship(back_populates="pair", uselist=False, cascade="all, delete-orphan",
                                                     passive_deletes=True)

    __table_args__ = (
        CheckConstraint("application_a_id <> application_b_id", name="ck_case_pairs_distinct_applications"),
        CheckConstraint("document_a_id IS NULL OR document_b_id IS NULL OR document_a_id <> document_b_id",
                        name="ck_case_pairs_distinct_documents"),
        CheckConstraint("ground_truth_label IS NULL OR is_evaluation_fixture = 1",
                        name="ck_case_pairs_ground_truth_fixture_only"),
        Index("ix_case_pairs_documents", "document_a_id", "document_b_id"),
    )


class MatchEvidence(Base):
    """System-generated evidence for one pair. Written once; reviewer actions never modify it."""

    __tablename__ = "match_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pair_id: Mapped[str] = mapped_column(String(36), ForeignKey("case_pairs.id", ondelete="CASCADE"), nullable=False,
                                         unique=True)
    exact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    text: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    visual: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    geometric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    matched_pages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    uncertainties: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    stage_status: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # identities at evaluation time
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # L4 fusion record (supporting / contradicting / unavailable signals, rationale) and the evidence-grounded
    # explanation generated from it. NULL for pairs evaluated before migration 0008.
    fusion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    pair: Mapped[CasePair] = relationship(back_populates="evidence")


class CasePairReviewAction(Base):
    """Append-only reviewer dispositions for a case pair."""

    __tablename__ = "case_pair_review_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pair_id: Mapped[str] = mapped_column(String(36), ForeignKey("case_pairs.id", ondelete="CASCADE"), nullable=False,
                                         index=True)
    action_type: Mapped[PairActionType] = mapped_column(str_enum(PairActionType, "pair_action_type"), nullable=False)
    previous_status: Mapped[PairReviewStatus] = mapped_column(str_enum(PairReviewStatus, "pair_previous_status"),
                                                              nullable=False)
    new_status: Mapped[PairReviewStatus] = mapped_column(str_enum(PairReviewStatus, "pair_new_status"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)
    actor_username: Mapped[str] = mapped_column(String(60), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ReuseEvaluationRun(Base):
    """Stored A0/A1/A4 evaluation results on the synthetic fixture set (never production data)."""

    __tablename__ = "reuse_evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    created_by: Mapped[str] = mapped_column(String(60), nullable=False)
    eval_version: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_digest: Mapped[str] = mapped_column(String(32), nullable=False)
    config_version: Mapped[str] = mapped_column(String(40), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
