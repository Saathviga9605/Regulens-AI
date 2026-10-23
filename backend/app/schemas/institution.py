from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InstitutionType, RecordStatus
from app.schemas.common import PartialUpdateModel, StrictInputModel


class InstitutionCreate(StrictInputModel):
    name: str = Field(min_length=3, max_length=200)
    institution_type: InstitutionType
    state: str = Field(min_length=2, max_length=80)
    district: str = Field(min_length=2, max_length=80)
    address: str = Field(min_length=5, max_length=500)
    trust_name: str = Field(min_length=3, max_length=200)
    property_identifier: str = Field(min_length=3, max_length=100)


class InstitutionUpdate(PartialUpdateModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    institution_type: InstitutionType | None = None
    state: str | None = Field(default=None, min_length=2, max_length=80)
    district: str | None = Field(default=None, min_length=2, max_length=80)
    address: str | None = Field(default=None, min_length=5, max_length=500)
    trust_name: str | None = Field(default=None, min_length=3, max_length=200)
    property_identifier: str | None = Field(default=None, min_length=3, max_length=100)
    status: RecordStatus | None = None


class InstitutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    institution_code: str
    name: str
    institution_type: InstitutionType
    state: str
    district: str
    status: RecordStatus


class InstitutionRead(InstitutionSummary):
    address: str
    trust_name: str
    property_identifier: str
    created_at: datetime
    updated_at: datetime
