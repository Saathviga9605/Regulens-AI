"""Application-level append-only audit log.

``record`` adds an event to the caller's session so it commits (or rolls back) together with the action it
describes. ``record_now`` writes immediately in its own session — used for failures and denials where the main
transaction is not committed. There is no update/delete path in the API. This is NOT a cryptographically
tamper-evident or legally certified immutable store: anyone with direct database access can alter rows.

Details must be small, structured and safe: identifiers, counts, statuses and changed field names — never
document text, passwords, tokens or free-text questions.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import Actor, current_actor, current_request_id
from app.models import AuditEvent
from app.models.enums import AuditOutcome

logger = logging.getLogger("regulens.audit")

_FORBIDDEN_KEYS = {"password", "token", "text", "content", "question", "answer", "quote"}


def _clean(details: dict | None) -> dict:
    safe = {}
    for key, value in (details or {}).items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        if isinstance(value, str):
            value = value[:200]
        safe[key] = value
    return safe


def _event(action: str, resource_type: str, resource_id, application_id, outcome: AuditOutcome, details,
           actor: Actor | None) -> AuditEvent:
    actor = actor or current_actor.get()
    return AuditEvent(actor_user_id=actor.user_id, actor_username=actor.username, action=action,
                      resource_type=resource_type, resource_id=str(resource_id)[:64] if resource_id else None,
                      application_id=application_id, outcome=outcome, request_id=current_request_id.get(),
                      details=_clean(details))


def record(session: Session, action: str, resource_type: str, resource_id=None, *, application_id: str | None = None,
           outcome: AuditOutcome = AuditOutcome.SUCCESS, details: dict | None = None, actor: Actor | None = None) -> None:
    session.add(_event(action, resource_type, resource_id, application_id, outcome, details, actor))


def record_now(factory: sessionmaker, action: str, resource_type: str, resource_id=None, *,
               application_id: str | None = None, outcome: AuditOutcome = AuditOutcome.FAILURE,
               details: dict | None = None, actor: Actor | None = None) -> None:
    try:
        with factory() as session:
            session.add(_event(action, resource_type, resource_id, application_id, outcome, details, actor))
            session.commit()
    except Exception as exc:  # never let audit failure mask the original error
        logger.error("Could not write audit event", extra={"error_type": type(exc).__name__})


def list_events(session: Session, *, page: int, page_size: int, application_id: str | None = None,
                action: str | None = None, actor: str | None = None, outcome: AuditOutcome | None = None,
                resource_type: str | None = None) -> tuple[list[AuditEvent], int]:
    stmt = select(AuditEvent)
    if application_id:
        stmt = stmt.where(AuditEvent.application_id == application_id)
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if actor:
        stmt = stmt.where(AuditEvent.actor_username == actor)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                           .limit(page_size).offset((page - 1) * page_size)).scalars().all()
    return list(rows), total
