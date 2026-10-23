"""Local demo-account bootstrap: defaults, idempotency, safety guards."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app import cli
from app.core.config import REPO_ROOT, Settings
from app.core.security import verify_password
from app.db.init_db import init_db
from app.db.session import build_engine, build_session_factory
from app.models import AuditEvent, AuthSession, User
from app.models.enums import UserRole
from app.services import auth
from tests.conftest import make_settings


@pytest.fixture
def factory(tmp_path: Path):
    engine = build_engine(make_settings(tmp_path / "boot.db"))
    init_db(engine)
    yield build_session_factory(engine)
    engine.dispose()


def users(factory) -> dict[str, User]:
    with factory() as s:
        return {u.username: u for u in s.execute(select(User)).scalars()}


def test_defaults_match_env_example() -> None:
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    values = dict(re.findall(r"^(REGULENS_DEMO_[A-Z_]+)=(.*)$", example, re.M))
    defaults = Settings.model_fields
    for key, value in values.items():
        field = key.removeprefix("REGULENS_").lower()
        default = defaults[field].default
        assert str(default).lower() == value.strip().lower(), key


def test_bootstrap_creates_hashed_accounts_and_is_idempotent(factory, tmp_path) -> None:
    settings = make_settings(tmp_path / "boot.db")
    with factory() as s:
        assert auth.bootstrap_demo_users(s, settings) == [("demo.reviewer", "created"), ("demo.admin", "created")]
    created = users(factory)
    assert created["demo.reviewer"].role == UserRole.REVIEWER and created["demo.admin"].role == UserRole.ADMIN
    for u in created.values():
        assert u.password_hash.startswith("scrypt$") and "Demo2026" not in u.password_hash
    assert verify_password("Reviewer@Demo2026", created["demo.reviewer"].password_hash)
    with factory() as s:
        assert auth.bootstrap_demo_users(s, settings) == [("demo.reviewer", "unchanged"), ("demo.admin", "unchanged")]
    assert len(users(factory)) == 2
    with factory() as s:
        events = s.execute(select(AuditEvent).where(AuditEvent.action == "user.demo_bootstrap")).scalars().all()
        assert events and all("Demo2026" not in str(e.details) for e in events)


def test_bootstrap_reconciles_only_demo_accounts(factory, tmp_path) -> None:
    settings = make_settings(tmp_path / "boot.db")
    with factory() as s:
        other = auth.create_user(s, username="real.person", display_name="Real", role=UserRole.ADMIN, password="other-password-1")
        auth.bootstrap_demo_users(s, settings)
        reviewer = s.execute(select(User).where(User.username == "demo.reviewer")).scalar_one()
        reviewer.role, reviewer.is_active = UserRole.ADMIN, False
        s.add(AuthSession(token_hash="x" * 64, user_id=reviewer.id, expires_at=reviewer.created_at.replace(year=2999)))
        s.commit()
        changed = make_settings(tmp_path / "boot.db", demo_reviewer_password="New-Reviewer-Pass")
        assert auth.bootstrap_demo_users(s, changed)[0] == ("demo.reviewer", "updated")
        reviewer = s.execute(select(User).where(User.username == "demo.reviewer")).scalar_one()
        assert reviewer.role == UserRole.REVIEWER and reviewer.is_active
        assert verify_password("New-Reviewer-Pass", reviewer.password_hash)
        assert s.execute(select(AuthSession).where(AuthSession.user_id == reviewer.id)).scalar_one().revoked_at
        untouched = s.get(User, other.id)
        assert untouched.role == UserRole.ADMIN and verify_password("other-password-1", untouched.password_hash)


def test_production_and_disabled_guards(factory, tmp_path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path / "x.db", environment="production", demo_users_enabled=True)  # explicit request refused
    implicit = make_settings(tmp_path / "x.db", environment="production")  # local default never carries into production
    assert implicit.demo_users_enabled is False
    prod = make_settings(tmp_path / "x.db", environment="production", demo_users_enabled=False)
    with factory() as s:
        with pytest.raises(auth.DemoBootstrapRefused):
            auth.bootstrap_demo_users(s, prod)
        with pytest.raises(auth.DemoBootstrapRefused):
            auth.bootstrap_demo_users(s, implicit)
        with pytest.raises(auth.DemoBootstrapRefused):
            auth.bootstrap_demo_users(s, make_settings(tmp_path / "x.db", demo_users_enabled=False))
    assert users(factory) == {}
    with pytest.raises(ValidationError):
        make_settings(tmp_path / "x.db", demo_admin_password="short")
    with pytest.raises(ValidationError):
        make_settings(tmp_path / "x.db", demo_admin_username="demo.reviewer")


def test_cli_seed_bootstraps_and_never_prints_passwords(tmp_path, monkeypatch, capsys) -> None:
    db = tmp_path / "cli.db"
    monkeypatch.setattr(cli, "get_settings", lambda: make_settings(db))
    assert cli.main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "Demo account 'demo.reviewer': created" in out and "LOCAL DEMO ONLY" in out
    assert "Reviewer@Demo2026" not in out and "Admin@Demo2026" not in out
    assert cli.main(["create-demo-users"]) == 0
    assert "unchanged" in capsys.readouterr().out
    monkeypatch.setattr(cli, "get_settings", lambda: make_settings(db, demo_users_enabled=False))
    assert cli.main(["create-demo-users"]) == 2


def test_demo_login_works_and_system_info_has_no_credentials(app, anon, settings) -> None:
    with app.state.session_factory() as s:
        auth.bootstrap_demo_users(s, settings)
    r = anon.post("/api/v1/auth/login", json={"username": "demo.reviewer", "password": "Reviewer@Demo2026"})
    assert r.status_code == 200 and "password" not in r.text.lower()
    info = anon.get("/api/v1/system/info").json()
    assert info["demo_mode"] is True and "Demo2026" not in str(info)
