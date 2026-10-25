"""Source-verification status (Project Bible v3.0 labels) and source type on verification attempts.

Explicit new columns (no repurposing of ``outcome``), backfilled from the existing adapter outcome:
simulated_match→verified, simulated_mismatch→mismatch_detected, simulated_expired→expired,
simulated_unavailable→source_unavailable, manual_review→manual_review_required,
unsupported→manual_review_required with source type NOT_CONNECTED. Existing rows were all produced by the
simulated adapter, so their source type is SIMULATED (never LIVE).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

STATUSES = ("verified", "mismatch_detected", "expired", "verification_pending", "source_unavailable",
            "manual_review_required")
TYPES = ("LIVE", "SIMULATED", "NOT_CONNECTED")


def _enum(values, name):
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=40)


def upgrade() -> None:
    # Plain ADD COLUMN (no table rebuild); the backfill runs before NOT NULL is enforced.
    op.add_column("verification_attempts", sa.Column("source_status", sa.String(40), nullable=True))
    op.add_column("verification_attempts", sa.Column("source_type", sa.String(40), nullable=True))
    op.execute("""
        UPDATE verification_attempts SET
          source_status = CASE outcome
            WHEN 'simulated_match' THEN 'verified'
            WHEN 'simulated_mismatch' THEN 'mismatch_detected'
            WHEN 'simulated_expired' THEN 'expired'
            WHEN 'simulated_unavailable' THEN 'source_unavailable'
            ELSE 'manual_review_required' END,
          source_type = CASE WHEN outcome = 'unsupported' THEN 'NOT_CONNECTED'
                             WHEN simulated = 1 THEN 'SIMULATED' ELSE 'NOT_CONNECTED' END
    """)
    # One rebuild adds NOT NULL and the value CHECK constraints after every row has a valid value.
    with op.batch_alter_table("verification_attempts", recreate="always") as batch:
        batch.alter_column("source_status", existing_type=sa.String(40), nullable=False)
        batch.alter_column("source_type", existing_type=sa.String(40), nullable=False)
        batch.create_check_constraint("issuer_source_status", sa.column("source_status").in_(STATUSES))
        batch.create_check_constraint("source_type", sa.column("source_type").in_(TYPES))


def downgrade() -> None:
    with op.batch_alter_table("verification_attempts") as batch:
        batch.drop_constraint("source_type", type_="check")
        batch.drop_constraint("issuer_source_status", type_="check")
        batch.drop_column("source_type")
        batch.drop_column("source_status")
