from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApplicationCategory, ApplicationStatus, ApplicationType, ProgrammeLevel, Shift
from app.schemas.common import AcademicYear, PartialUpdateModel, StrictInputModel
from app.schemas.institution import InstitutionSummary

# strict=True rejects strings ("60") and floats (60.5) for intake values.
Intake = Annotated[int, Field(ge=0, le=600, strict=True)]
InstitutionCode = Annotated[str, Field(min_length=3, max_length=20)]


class ProgrammeIn(StrictInputModel):
    programme_level: ProgrammeLevel
    course_name: str = Field(min_length=2, max_length=150)
    shift: Shift = Shift.FIRST
    existing_intake: Intake
    proposed_intake: Intake


class ProgrammeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    programme_level: ProgrammeLevel
    course_name: str
    shift: Shift
    existing_intake: int
    proposed_intake: int


Programmes = Annotated[list[ProgrammeIn], Field(min_length=1, max_length=20)]


class ApplicationCreate(StrictInputModel):
    institution_code: InstitutionCode
    category: Literal[ApplicationCategory.EXTENSION_OF_APPROVAL] = ApplicationCategory.EXTENSION_OF_APPROVAL
    academic_year: AcademicYear
    application_type: ApplicationType
    programmes: Programmes


class ApplicationUpdate(PartialUpdateModel):
    """Draft-only edits. Status, IDs and timestamps cannot be set here."""

    institution_code: InstitutionCode | None = None
    academic_year: AcademicYear | None = None
    application_type: ApplicationType | None = None
    programmes: Programmes | None = None


class StatusChangeRequest(StrictInputModel):
    target_status: ApplicationStatus


class ApplicationListItem(BaseModel):
    application_code: str
    category: ApplicationCategory
    academic_year: str
    application_type: ApplicationType
    status: ApplicationStatus
    institution: InstitutionSummary
    programme_count: int
    total_proposed_intake: int
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationRead(ApplicationListItem):
    programmes: list[ProgrammeRead]
    status_changed_at: datetime
    is_editable: bool
    allowed_transitions: list[ApplicationStatus]
    institution_snapshot: dict | None = Field(
        description="Institution details as recorded when the application was marked ready; null while draft."
    )
