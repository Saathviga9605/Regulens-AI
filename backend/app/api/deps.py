"""Shared FastAPI dependencies, including authentication and role checks.

``get_current_actor`` is applied at router level (``api/v1/router.py``) to every protected router, and
``require_admin`` to administrator-only routes. Both are async so the actor context variable they set is visible
to the (threadpool-executed) endpoint and to audit records.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import Actor, current_actor
from app.core.errors import AppError
from app.db.session import session_scope
from app.models.enums import AuditOutcome
from app.schemas.common import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services import audit
from app.services.auth import resolve_token
from app.services.storage import DocumentStorage


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


def get_storage(request: Request) -> DocumentStorage:
    return request.app.state.document_storage


def get_db(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _unauthenticated() -> AppError:
    error = AppError(401, "not_authenticated", "Sign in to continue.")
    error.headers = {"WWW-Authenticate": "Bearer"}
    return error


async def get_current_actor(request: Request) -> Actor:
    token = bearer_token(request)
    if not token:
        raise _unauthenticated()
    with request.app.state.session_factory() as session:
        resolved = resolve_token(session, token)
        if resolved is None:
            raise _unauthenticated()
        _, user = resolved
        actor = Actor(user.id, user.username, user.role, bool(user.cross_case_reviewer))
    current_actor.set(actor)
    request.state.actor = actor
    return actor


async def require_cross_case_reviewer(request: Request, actor: Actor = Depends(get_current_actor)) -> Actor:
    """Linked-case identities, documents, page images and match evidence need the explicit cross-case permission.
    The administrator role alone does not grant it. Refusals are audited with the pair id (no content)."""
    if not actor.cross_case_reviewer:
        pair_id = request.path_params.get("pair_id")
        audit.record_now(request.app.state.session_factory, "cross_case.access_denied", "case_pair",
                         pair_id or f"{request.method} {request.url.path}"[:64], outcome=AuditOutcome.DENIED,
                         details={"pair_id": pair_id, "action": f"{request.method} {request.url.path}"[:120],
                                  "required_permission": "cross_case_reviewer"}, actor=actor)
        raise AppError(403, "cross_case_permission_required",
                       "Cross-case match details require the cross-case reviewer permission.")
    return actor


async def require_admin(request: Request, actor: Actor = Depends(get_current_actor)) -> Actor:
    if not actor.is_admin:
        audit.record_now(request.app.state.session_factory, "authorization.denied", "endpoint",
                         f"{request.method} {request.url.path}"[:64], outcome=AuditOutcome.DENIED,
                         details={"required_role": "admin"}, actor=actor)
        raise AppError(403, "forbidden", "This action requires the administrator role.")
    return actor
