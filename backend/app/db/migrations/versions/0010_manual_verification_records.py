"""Reviewer-recorded (manual) source-verification results.

Adds the ``reviewer_recorded`` adapter outcome and ``verification_attempts.recorded_by``. Existing rows are unchanged.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

OLD = ("simulated_match", "simulated_mismatch", "simulated_expired", "simulated_unavailable", "manual_review",
       "unsupported")
NEW = OLD + ("reviewer_recorded",)


def _enum(values):
    return sa.Enum(*values, name="verification_outcome", native_enum=False, create_constraint=True, length=40)


def upgrade() -> None:
    op.add_column("verification_attempts", sa.Column("recorded_by", sa.String(60), nullable=True))
    with op.batch_alter_table("verification_attempts") as batch:
        batch.alter_column("outcome", existing_type=_enum(OLD), type_=_enum(NEW), existing_nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM verification_attempts WHERE outcome = 'reviewer_recorded' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while reviewer-recorded verification results exist.")
    with op.batch_alter_table("verification_attempts") as batch:
        batch.alter_column("outcome", existing_type=_enum(NEW), type_=_enum(OLD), existing_nullable=False)
        batch.drop_column("recorded_by")
