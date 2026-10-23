import math
import re
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class StrictInputModel(BaseModel):
    """Base for request bodies: unknown fields (e.g. ids, timestamps) are rejected, strings stripped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PartialUpdateModel(StrictInputModel):
    """PATCH body: omitted fields are left unchanged; explicit null is rejected."""

    @model_validator(mode="after")
    def _no_explicit_nulls(self):
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f"Fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(items=items, total=total, page=page, page_size=page_size,
                   total_pages=math.ceil(total / page_size) if total else 0)


_ACADEMIC_YEAR = re.compile(r"^(\d{4})-(\d{2})$")


def validate_academic_year(value: str) -> str:
    """Academic years look like '2026-27': start year 2000-2099 followed by the next year's last two digits."""
    match = _ACADEMIC_YEAR.match(value)
    if not match:
        raise ValueError("Academic year must use the format YYYY-YY, e.g. 2026-27.")
    start, end = int(match.group(1)), int(match.group(2))
    if not 2000 <= start <= 2099:
        raise ValueError("Academic year must start between 2000 and 2099.")
    if end != (start + 1) % 100:
        raise ValueError("Academic year must span consecutive years, e.g. 2026-27.")
    return value


AcademicYear = Annotated[str, Field(min_length=7, max_length=7), AfterValidator(validate_academic_year)]
