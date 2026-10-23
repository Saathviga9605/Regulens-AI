"""Shared FastAPI dependencies.

Authorization (planned) will be added as a router-level dependency in ``api/v1/router.py``
so individual routes do not need rewriting.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import session_scope
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int


def get_pagination(
    page: int = Query(1, ge=1, le=100_000),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)
