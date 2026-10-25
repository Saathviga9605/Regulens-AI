"""OCR evidence coordinates and confidence; evidence fusion and explanation records.

Additive only. Existing rows get empty line lists, no OCR metadata and no fusion record; documents are re-processed
lazily because the extractor version (part of the processing pipeline version) changed.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("document_pages") as batch:
        batch.add_column(sa.Column("lines", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("ocr_engine", sa.String(80), nullable=True))
        batch.add_column(sa.Column("ocr_confidence", sa.Float(), nullable=True))
        batch.add_column(sa.Column("rotation_degrees", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("extracted_fields") as batch:
        batch.add_column(sa.Column("evidence_source", sa.String(20), nullable=True))
        batch.add_column(sa.Column("evidence_box", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ocr_confidence", sa.Float(), nullable=True))
    with op.batch_alter_table("match_evidence") as batch:
        batch.add_column(sa.Column("fusion", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("explanation", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("match_evidence") as batch:
        batch.drop_column("explanation")
        batch.drop_column("fusion")
    with op.batch_alter_table("extracted_fields") as batch:
        batch.drop_column("ocr_confidence")
        batch.drop_column("evidence_box")
        batch.drop_column("evidence_source")
    with op.batch_alter_table("document_pages") as batch:
        batch.drop_column("rotation_degrees")
        batch.drop_column("ocr_confidence")
        batch.drop_column("ocr_engine")
        batch.drop_column("lines")
