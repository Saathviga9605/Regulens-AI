"""Local prototype authentication: users, password login, server-side sessions, user administration."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.context import Actor
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security import DUMMY_HASH, MIN_PASSWORD_LENGTH, hash_password, new_token, token_hash, verify_password
from app.db.types import utcnow
from app.models import AuditEvent, AuthSession, User
from app.models.enums import AuditOutcome, UserRole
from app.services import audit


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AppError(422, "validation_error", f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                       [{"loc": ["body", "password"], "msg": "Too short."}])


def create_user(session: Session, *, username: str, display_name: str, role: UserRole, password: str) -> User:
    _check_password(password)
    username = username.strip().lower()
    if session.execute(select(User.id).where(User.username == username)).first():
        raise ConflictError("user_exists", f"User '{username}' already exists.")
    user = User(username=username, display_name=display_name.strip(), role=role, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    audit.record(session, "user.created", "user", user.id, details={"username": username, "role": role.value})
    session.commit()
    return user


def update_user(session: Session, user_id: str, actor: Actor, *, role: UserRole | None = None,
                is_active: bool | None = None, display_name: str | None = None, password: str | None = None,
                cross_case_reviewer: bool | None = None) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("User was not found.")
    if user.id == actor.user_id and ((role and role != UserRole.ADMIN) or is_active is False):
        raise ConflictError("self_lockout", "You cannot remove your own administrator role or deactivate yourself.")
    if user.id == actor.user_id and cross_case_reviewer is not None and cross_case_reviewer != user.cross_case_reviewer:
        raise ConflictError("self_permission_change",
                            "You cannot change your own cross-case reviewer permission; ask another administrator.")
    changed = []
    if role is not None and role != user.role:
        changed.append("role")
        audit.record(session, "user.role_changed", "user", user.id,
                     details={"username": user.username, "from": user.role.value, "to": role.value})
        user.role = role
    if is_active is not None and is_active != user.is_active:
        changed.append("is_active")
        user.is_active = is_active
    if cross_case_reviewer is not None and cross_case_reviewer != user.cross_case_reviewer:
        changed.append("cross_case_reviewer")
        audit.record(session, "user.permission_changed", "user", user.id,
                     details={"username": user.username, "permission": "cross_case_reviewer",
                              "granted": cross_case_reviewer})
        user.cross_case_reviewer = cross_case_reviewer
    if display_name is not None and display_name.strip() != user.display_name:
        changed.append("display_name")
        user.display_name = display_name.strip()
    if password is not None:
        _check_password(password)
        changed.append("password")
        user.password_hash = hash_password(password)
    if changed:
        user.updated_at = utcnow()
        if {"password", "is_active", "role", "cross_case_reviewer"} & set(changed):
            _revoke_all(session, user.id)  # privilege/credential change ends existing sessions
        audit.record(session, "user.updated", "user", user.id,
                     details={"username": user.username, "changed": changed, "is_active": user.is_active})
        session.commit()
    return user


def _revoke_all(session: Session, user_id: str) -> None:
    for s in session.execute(select(AuthSession).where(AuthSession.user_id == user_id,
                                                       AuthSession.revoked_at.is_(None))).scalars():
        s.revoked_at = utcnow()


def _recent_failures(session: Session, username: str, settings: Settings) -> int:
    since = utcnow() - timedelta(minutes=settings.login_lockout_minutes)
    return session.execute(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.action == "auth.login", AuditEvent.outcome == AuditOutcome.FAILURE,
        AuditEvent.resource_id == username[:64], AuditEvent.created_at >= since)).scalar_one()


def login(session: Session, settings: Settings, username: str, password: str) -> tuple[str, AuthSession, User]:
    username = username.strip().lower()
    if _recent_failures(session, username, settings) >= settings.login_max_failures:
        audit.record(session, "auth.login", "user", username, outcome=AuditOutcome.DENIED,
                     details={"reason": "too_many_failures"}, actor=Actor(None, username[:60], None))
        session.commit()
        raise AppError(429, "too_many_attempts", "Too many failed sign-in attempts. Try again later.")
    user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        audit.record(session, "auth.login", "user", username, outcome=AuditOutcome.FAILURE,
                     details={"reason": "invalid_credentials"}, actor=Actor(None, username[:60], None))
        session.commit()
        raise AppError(401, "invalid_credentials", "Invalid username or password.")
    token = new_token()
    auth_session = AuthSession(token_hash=token_hash(token), user_id=user.id,
                               expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes))
    session.add(auth_session)
    audit.record(session, "auth.login", "user", user.username, details={"role": user.role.value},
                 actor=Actor(user.id, user.username, user.role))
    session.commit()
    return token, auth_session, user


def resolve_token(session: Session, token: str) -> tuple[AuthSession, User] | None:
    row = session.execute(select(AuthSession).where(AuthSession.token_hash == token_hash(token))).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at <= utcnow() or not row.user.is_active:
        return None
    return row, row.user


def logout(session: Session, token: str) -> None:
    resolved = resolve_token(session, token)
    if resolved:
        resolved[0].revoked_at = utcnow()
        audit.record(session, "auth.logout", "user", resolved[1].username)
        session.commit()


def list_users(session: Session) -> list[User]:
    return list(session.execute(select(User).order_by(User.username)).scalars())


class DemoBootstrapRefused(Exception):
    pass


def bootstrap_demo_users(session: Session, settings: Settings) -> list[tuple[str, str]]:
    """Create or reconcile the two LOCAL DEMO accounts from settings. Idempotent.

    Rules: only the configured demo usernames are touched (other users never are). A missing account is created.
    An existing one is set to the configured role, re-activated, and its password re-hashed only if the configured
    password no longer verifies (its sessions are then revoked). Passwords are stored only as scrypt hashes and are
    never printed, logged or audited. Refused in production or when REGULENS_DEMO_USERS_ENABLED is false.
    Returns [(username, "created" | "updated" | "unchanged")].
    """
    if settings.environment == "production":
        raise DemoBootstrapRefused("Demo accounts are never bootstrapped in production.")
    if not settings.demo_users_enabled:
        raise DemoBootstrapRefused("Demo accounts are disabled (REGULENS_DEMO_USERS_ENABLED=false).")
    accounts = [
        (settings.demo_reviewer_username, "Demo Reviewer (local demo)", UserRole.REVIEWER, settings.demo_reviewer_password),
        (settings.demo_admin_username, "Demo Administrator (local demo)", UserRole.ADMIN, settings.demo_admin_password),
    ]
    results = []
    for username, display_name, role, password in accounts:
        _check_password(password)
        username = username.strip().lower()
        user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if user is None:
            user = User(username=username, display_name=display_name, role=role, password_hash=hash_password(password))
            session.add(user)
            session.flush()
            results.append((username, "created"))
        else:
            changed = []
            if user.role != role:
                user.role = role
                changed.append("role")
            if not user.is_active:
                user.is_active = True
                changed.append("is_active")
            if not verify_password(password, user.password_hash):
                user.password_hash = hash_password(password)
                changed.append("password")
            if changed:
                user.updated_at = utcnow()
                _revoke_all(session, user.id)
            results.append((username, "updated" if changed else "unchanged"))
        audit.record(session, "user.demo_bootstrap", "user", user.id,
                     details={"username": username, "role": role.value, "result": results[-1][1]})
    session.commit()
    return results
