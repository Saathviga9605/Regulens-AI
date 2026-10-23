import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, str_enum, utcnow
from app.models.enums import ApplicationCategory, ApplicationStatus, ApplicationType, ProgrammeLevel, Shift
from app.models.institution import Institution


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category: Mapped[ApplicationCategory] = mapped_column(
        str_enum(ApplicationCategory, "application_category"), nullable=False,
        default=ApplicationCategory.EXTENSION_OF_APPROVAL,
    )
    academic_year: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    application_type: Mapped[ApplicationType] = mapped_column(
        str_enum(ApplicationType, "application_type"), nullable=False, index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        str_enum(ApplicationStatus, "application_status"), nullable=False, default=ApplicationStatus.DRAFT, index=True
    )
    # Internal "marked ready" timestamp. Not an official AICTE submission date.
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    # Institution details captured when the application is frozen, so later institution
    # edits do not rewrite what this application recorded.
    institution_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    institution: Mapped[Institution] = relationship(back_populates="applications")
    programmes: Mapped[list["ApplicationProgramme"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationProgramme.position"
    )

    __table_args__ = (
        Index("ix_applications_created", "created_at", "application_code"),
    )


class ApplicationProgramme(Base):
    __tablename__ = "application_programmes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    programme_level: Mapped[ProgrammeLevel] = mapped_column(str_enum(ProgrammeLevel, "programme_level"), nullable=False)
    course_name: Mapped[str] = mapped_column(String(150), nullable=False)
    shift: Mapped[Shift] = mapped_column(str_enum(Shift, "programme_shift"), nullable=False, default=Shift.FIRST)
    existing_intake: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_intake: Mapped[int] = mapped_column(Integer, nullable=False)

    application: Mapped[Application] = relationship(back_populates="programmes")

    __table_args__ = (
        UniqueConstraint("application_id", "programme_level", "course_name", "shift", name="uq_programme_per_app"),
        CheckConstraint("existing_intake >= 0 AND existing_intake <= 600", name="ck_programme_existing_intake"),
        CheckConstraint("proposed_intake >= 0 AND proposed_intake <= 600", name="ck_programme_proposed_intake"),
    )


class IdSequence(Base):
    """Named counters for human-readable IDs, incremented atomically in the database."""

    __tablename__ = "id_sequences"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
