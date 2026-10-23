import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, str_enum, utcnow
from app.models.enums import InstitutionType, RecordStatus

if TYPE_CHECKING:
    from app.models.application import Application


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    institution_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    institution_type: Mapped[InstitutionType] = mapped_column(str_enum(InstitutionType, "institution_type"), nullable=False)
    state: Mapped[str] = mapped_column(String(80), nullable=False)
    district: Mapped[str] = mapped_column(String(80), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    trust_name: Mapped[str] = mapped_column(String(200), nullable=False)
    property_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(str_enum(RecordStatus, "record_status"), nullable=False,
                                                 default=RecordStatus.ACTIVE)
    # Set only for records inserted by the synthetic seed; lets reseeding stay idempotent.
    seed_key: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    applications: Mapped[list["Application"]] = relationship(back_populates="institution")

    __table_args__ = (Index("ix_institutions_state_district", "state", "district"),)
