"""Shared query helpers: safe LIKE patterns and pagination."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

LIKE_ESCAPE = "\\"


def contains_pattern(term: str) -> str:
    """Case-insensitive 'contains' pattern with LIKE wildcards in user input escaped."""
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def paginate(session: Session, stmt: Select, page: int, page_size: int) -> tuple[list, int]:
    total = session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = session.execute(stmt.limit(page_size).offset((page - 1) * page_size)).unique().scalars().all()
    return list(rows), total
