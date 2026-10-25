"""Support APH document alternatives in the registry evaluator.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

OLD_CATEGORIES = (
    "fire_safety_certificate", "occupancy_certificate", "completion_certificate",
    "structural_stability_certificate", "building_plan", "university_noc", "trust_resolution", "other",
)
NEW_CATEGORIES = (
    "fire_safety_certificate", "occupancy_certificate", "completion_certificate", "building_license", "form_d",
    "structural_stability_certificate", "building_plan", "university_noc", "trust_resolution", "other",
)
OLD_RULE_TYPES = (
    "expected_document", "required_field", "processing_quality", "classification_consistency",
    "institution_name_match", "field_consistency", "area_consistency", "date_order",
    "expiry_before_scrutiny", "simulated_issuer_outcome", "validity_period", "conditional_document",
    "issuer_authority",
)
NEW_RULE_TYPES = OLD_RULE_TYPES + ("alternative_document_group",)


def _enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=40)


def upgrade() -> None:
    for table, column, enum_name in (
        ("documents", "category", "document_category"),
        ("document_processing", "predicted_category", "predicted_category"),
        ("issuer_reference_records", "document_category", "reference_category"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=_enum(OLD_CATEGORIES, enum_name),
                type_=_enum(NEW_CATEGORIES, enum_name),
                existing_nullable=column == "predicted_category",
            )

    with op.batch_alter_table("scrutiny_rules") as batch:
        batch.alter_column(
            "rule_type",
            existing_type=_enum(OLD_RULE_TYPES, "rule_type"),
            type_=_enum(NEW_RULE_TYPES, "rule_type"),
            existing_nullable=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT 1 FROM scrutiny_rules WHERE rule_type = 'alternative_document_group' LIMIT 1"
        )
    ).first():
        raise RuntimeError("Cannot downgrade while rules use the alternative document evaluator.")
    for table, column in (
        ("documents", "category"),
        ("document_processing", "predicted_category"),
        ("issuer_reference_records", "document_category"),
    ):
        if connection.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE {column} IN ('building_license', 'form_d') LIMIT 1")
        ).first():
            raise RuntimeError(f"Cannot downgrade while {table}.{column} uses APH document categories.")

    with op.batch_alter_table("scrutiny_rules") as batch:
        batch.alter_column(
            "rule_type",
            existing_type=_enum(NEW_RULE_TYPES, "rule_type"),
            type_=_enum(OLD_RULE_TYPES, "rule_type"),
            existing_nullable=False,
        )
    for table, column, enum_name in (
        ("documents", "category", "document_category"),
        ("document_processing", "predicted_category", "predicted_category"),
        ("issuer_reference_records", "document_category", "reference_category"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                column,
                existing_type=_enum(NEW_CATEGORIES, enum_name),
                type_=_enum(OLD_CATEGORIES, enum_name),
                existing_nullable=column == "predicted_category",
            )
