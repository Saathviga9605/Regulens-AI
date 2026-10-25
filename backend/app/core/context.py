"""Per-request context (actor, request id) for audit records.

Set by the request-id middleware and the authentication dependency (both run in the request's own context,
so the values are visible to sync endpoints executed in the threadpool). Outside requests (CLI, seed) the
actor is the system.
"""

from contextvars import ContextVar
from dataclasses import dataclass

from app.models.enums import UserRole


@dataclass(frozen=True)
class Actor:
    user_id: str | None
    username: str
    role: UserRole | None
    # Senior cross-case review permission (linked-case identities and match evidence). Independent of role.
    cross_case_reviewer: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


SYSTEM_ACTOR = Actor(None, "system", None)

current_actor: ContextVar[Actor] = ContextVar("current_actor", default=SYSTEM_ACTOR)
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)
