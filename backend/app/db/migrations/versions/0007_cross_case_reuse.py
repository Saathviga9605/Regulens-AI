"""Cross-case document reuse: fingerprints, scan runs, case pairs, match evidence, pair review actions,
stored evaluations; per-user cross-case review permission.

Additive only: new tables and one boolean column on ``users`` (default false). Existing data is untouched.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

OUTCOMES = ("MATCH_CONFIRMED_FOR_REVIEW", "CANDIDATE", "NOT_MATCHED", "INCONCLUSIVE")
SCAN_STATUSES = ("running", "completed", "failed")
PAIR_STATUSES = ("not_reviewed", "confirmed_candidate", "dismissed", "escalated")
PAIR_ACTIONS = ("confirm_candidate", "dismiss", "escalate", "note")


def _enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=40)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("cross_case_reviewer", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "document_fingerprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("feature_version", sa.String(120), nullable=False),
        sa.Column("text_fingerprint", sa.String(64), nullable=True),
        sa.Column("text_chars", sa.Integer(), nullable=False),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_id", "feature_version", name="uq_fingerprint_document_version"),
    )
    op.create_index("ix_document_fingerprints_text_fingerprint", "document_fingerprints", ["text_fingerprint"])

    op.create_table(
        "reuse_scan_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", _enum(SCAN_STATUSES, "reuse_scan_status"), nullable=False),
        sa.Column("pipeline_version", sa.String(120), nullable=False),
        sa.Column("config_version", sa.String(40), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("triggered_by", sa.String(60), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("documents_scanned", sa.Integer(), nullable=False),
        sa.Column("comparisons", sa.Integer(), nullable=False),
        sa.Column("candidates", sa.Integer(), nullable=False),
        sa.Column("pairs_created", sa.Integer(), nullable=False),
        sa.Column("pairs_reused", sa.Integer(), nullable=False),
        sa.Column("outcome_counts", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.String(500), nullable=True),
    )
    op.create_index("ix_reuse_scan_runs_application_started", "reuse_scan_runs", ["application_id", "started_at"])

    op.create_table(
        "case_pairs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("input_key", sa.String(64), nullable=False, unique=True),
        sa.Column("document_a_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_b_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("application_a_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("application_b_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sha256_a", sa.String(64), nullable=False),
        sa.Column("sha256_b", sa.String(64), nullable=False),
        sa.Column("candidate_methods", sa.JSON(), nullable=False),
        sa.Column("outcome", _enum(OUTCOMES, "reuse_outcome"), nullable=False),
        sa.Column("candidate_score", sa.Float(), nullable=True),
        sa.Column("pipeline_version", sa.String(120), nullable=False),
        sa.Column("config_version", sa.String(40), nullable=False),
        sa.Column("review_status", _enum(PAIR_STATUSES, "pair_review_status"), nullable=False),
        sa.Column("review_version", sa.Integer(), nullable=False),
        sa.Column("first_run_id", sa.String(36), sa.ForeignKey("reuse_scan_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_run_id", sa.String(36), sa.ForeignKey("reuse_scan_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_evaluation_fixture", sa.Boolean(), nullable=False),
        sa.Column("ground_truth_label", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("application_a_id <> application_b_id", name="ck_case_pairs_distinct_applications"),
        sa.CheckConstraint("document_a_id IS NULL OR document_b_id IS NULL OR document_a_id <> document_b_id",
                           name="ck_case_pairs_distinct_documents"),
        sa.CheckConstraint("ground_truth_label IS NULL OR is_evaluation_fixture = 1",
                           name="ck_case_pairs_ground_truth_fixture_only"),
    )
    op.create_index("ix_case_pairs_application_a_id", "case_pairs", ["application_a_id"])
    op.create_index("ix_case_pairs_application_b_id", "case_pairs", ["application_b_id"])
    op.create_index("ix_case_pairs_outcome", "case_pairs", ["outcome"])
    op.create_index("ix_case_pairs_documents", "case_pairs", ["document_a_id", "document_b_id"])

    op.create_table(
        "match_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pair_id", sa.String(36), sa.ForeignKey("case_pairs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("exact", sa.JSON(), nullable=False),
        sa.Column("text", sa.JSON(), nullable=False),
        sa.Column("visual", sa.JSON(), nullable=False),
        sa.Column("geometric", sa.JSON(), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("matched_pages", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("uncertainties", sa.JSON(), nullable=False),
        sa.Column("stage_status", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "case_pair_review_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pair_id", sa.String(36), sa.ForeignKey("case_pairs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", _enum(PAIR_ACTIONS, "pair_action_type"), nullable=False),
        sa.Column("previous_status", _enum(PAIR_STATUSES, "pair_previous_status"), nullable=False),
        sa.Column("new_status", _enum(PAIR_STATUSES, "pair_new_status"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_username", sa.String(60), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_case_pair_review_actions_pair_id", "case_pair_review_actions", ["pair_id"])

    op.create_table(
        "reuse_evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(60), nullable=False),
        sa.Column("eval_version", sa.String(40), nullable=False),
        sa.Column("dataset_version", sa.String(40), nullable=False),
        sa.Column("dataset_digest", sa.String(32), nullable=False),
        sa.Column("config_version", sa.String(40), nullable=False),
        sa.Column("pipeline_version", sa.String(120), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
    )
    op.create_index("ix_reuse_evaluation_runs_created_at", "reuse_evaluation_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_reuse_evaluation_runs_created_at", table_name="reuse_evaluation_runs")
    op.drop_table("reuse_evaluation_runs")
    op.drop_index("ix_case_pair_review_actions_pair_id", table_name="case_pair_review_actions")
    op.drop_table("case_pair_review_actions")
    op.drop_table("match_evidence")
    for name in ("ix_case_pairs_documents", "ix_case_pairs_outcome", "ix_case_pairs_application_b_id",
                 "ix_case_pairs_application_a_id"):
        op.drop_index(name, table_name="case_pairs")
    op.drop_table("case_pairs")
    op.drop_index("ix_reuse_scan_runs_application_started", table_name="reuse_scan_runs")
    op.drop_table("reuse_scan_runs")
    op.drop_index("ix_document_fingerprints_text_fingerprint", table_name="document_fingerprints")
    op.drop_table("document_fingerprints")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("cross_case_reviewer")
