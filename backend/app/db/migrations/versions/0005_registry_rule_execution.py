"""Registry evaluator support, provenance, and explicit scrutiny reference dates.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

OLD_RULE_TYPES = (
    "expected_document", "required_field", "processing_quality", "classification_consistency",
    "institution_name_match", "field_consistency", "area_consistency", "date_order",
    "expiry_before_scrutiny", "simulated_issuer_outcome",
)
NEW_RULE_TYPES = OLD_RULE_TYPES + ("validity_period", "conditional_document", "issuer_authority")


def _rule_type_enum(values):
    return sa.Enum(*values, name="rule_type", native_enum=False, create_constraint=True, length=40)


def upgrade() -> None:
    with op.batch_alter_table("scrutiny_rules") as batch:
        batch.alter_column("rule_type", existing_type=_rule_type_enum(OLD_RULE_TYPES),
                           type_=_rule_type_enum(NEW_RULE_TYPES), existing_nullable=False)
        batch.add_column(sa.Column("provenance", sa.String(length=20), nullable=False, server_default="demo"))
        batch.add_column(sa.Column("registry_managed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("effective_from", sa.String(length=10), nullable=True))
        batch.add_column(sa.Column("effective_to", sa.String(length=10), nullable=True))

    op.execute(
        "UPDATE scrutiny_rules SET provenance = CASE "
        "WHEN is_demo_only = 1 THEN 'demo' "
        "WHEN source_verification_status = 'not_applicable' THEN 'integrity' "
        "ELSE 'demo' END"
    )
    op.execute(
        "UPDATE scrutiny_rules SET enabled = 0, retired = 1, provenance = 'demo', "
        "source_verification_status = 'unverified' WHERE rule_id IN ('EXP-003', 'FLD-002')"
    )

    with op.batch_alter_table("scrutiny_runs") as batch:
        batch.alter_column("scrutiny_date", existing_type=sa.String(length=10), nullable=True)
        batch.add_column(sa.Column("scrutiny_date_source", sa.String(length=40), nullable=False,
                                   server_default="system_date_legacy"))

    op.execute(
        "UPDATE scrutiny_runs SET scrutiny_date_source = "
        "CASE WHEN scrutiny_date IS NULL THEN 'unavailable' ELSE 'system_date_legacy' END"
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_new_types = connection.execute(
        sa.text(
            "SELECT 1 FROM scrutiny_rules WHERE rule_type IN "
            "('validity_period', 'conditional_document', 'issuer_authority') LIMIT 1"
        )
    ).first()
    if has_new_types:
        raise RuntimeError("Cannot downgrade while rules use registry evaluator types.")

    with op.batch_alter_table("scrutiny_runs") as batch:
        batch.drop_column("scrutiny_date_source")
        batch.alter_column("scrutiny_date", existing_type=sa.String(length=10), nullable=False)

    with op.batch_alter_table("scrutiny_rules") as batch:
        batch.drop_column("effective_to")
        batch.drop_column("effective_from")
        batch.drop_column("retired")
        batch.drop_column("registry_managed")
        batch.drop_column("provenance")
        batch.alter_column("rule_type", existing_type=_rule_type_enum(NEW_RULE_TYPES),
                           type_=_rule_type_enum(OLD_RULE_TYPES), existing_nullable=False)
