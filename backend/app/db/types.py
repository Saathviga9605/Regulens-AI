"""Column types shared by ORM models."""

from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Enum
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC as naive datetimes (SQLite has no tz support); always returns aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware values.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR + CHECK constraint storing enum values (portable; no native DB enum)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=40,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )
