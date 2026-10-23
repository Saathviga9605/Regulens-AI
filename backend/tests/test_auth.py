"""Authentication, sessions and role-based access control."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models import AuditEvent, AuthSession, User
from app.db.types import utcnow
from tests.conftest import TEST_PASSWORD, authenticate


def test_password_hashing() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "garbage")
    assert hash_password("same-password-1") != hash_password("same-password-1")  # salted


def test_protected_endpoints_require_authentication(anon: TestClient) -> None:
    assert anon.get("/api/v1/health").status_code == 200  # public
    assert anon.get("/api/v1/system/info").status_code == 200
    for method, path in [("get", "/api/v1/applications"), ("get", "/api/v1/institutions"),
                         ("get", "/api/v1/scrutiny-rules"), ("get", "/api/v1/review-queue"),
                         ("get", "/api/v1/alerts"), ("get", "/api/v1/documents/x/content"),
                         ("post", "/api/v1/applications/REG-EoA-2026-0001/copilot")]:
        response = getattr(anon, method)(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "not_authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"
    anon.headers["Authorization"] = "Bearer forged-token"
    assert anon.get("/api/v1/applications").status_code == 401


def test_login_me_logout(app, client: TestClient, anon: TestClient) -> None:
    authenticate(anon, "reviewer", "alice.reviewer")
    me = anon.get("/api/v1/auth/me").json()
    assert me["username"] == "alice.reviewer" and me["role"] == "reviewer" and "password_hash" not in me
    with app.state.session_factory() as s:
        stored = s.execute(select(AuthSession)).scalars().all()
        token = anon.headers["Authorization"].split()[1]
        assert all(row.token_hash != token for row in stored)  # only hashes are stored
    assert anon.post("/api/v1/auth/logout").status_code == 204
    assert anon.get("/api/v1/auth/me").status_code == 401


def test_bad_credentials_and_lockout(client: TestClient, anon: TestClient, app) -> None:
    authenticate(TestClient(app), "reviewer", "bob")  # creates user
    for _ in range(5):
        r = anon.post("/api/v1/auth/login", json={"username": "bob", "password": "wrong-password"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    unknown = anon.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever-123"})
    assert unknown.json()["error"]["message"] == "Invalid username or password."  # no user enumeration
    locked = anon.post("/api/v1/auth/login", json={"username": "bob", "password": TEST_PASSWORD})
    assert locked.status_code == 429
    with app.state.session_factory() as s:
        events = s.execute(select(AuditEvent).where(AuditEvent.action == "auth.login")).scalars().all()
        assert {e.outcome.value for e in events} >= {"failure", "denied"}
        assert all("password" not in str(e.details) for e in events)


def test_expired_and_deactivated_sessions(app, client: TestClient, reviewer: TestClient) -> None:
    with app.state.session_factory() as s:
        for row in s.execute(select(AuthSession)).scalars():
            row.expires_at = utcnow() - timedelta(minutes=1)
        s.commit()
    assert reviewer.get("/api/v1/applications").status_code == 401
    authenticate(reviewer, "reviewer")
    with app.state.session_factory() as s:
        user_id = s.execute(select(User.id).where(User.username == "test.reviewer")).scalar_one()
    authenticate(client, "admin")
    assert client.patch(f"/api/v1/users/{user_id}", json={"is_active": False}).status_code == 200
    assert reviewer.get("/api/v1/applications").status_code == 401  # sessions revoked on deactivation


def test_reviewer_cannot_use_admin_endpoints(client: TestClient, reviewer: TestClient, app) -> None:
    rule = reviewer.get("/api/v1/scrutiny-rules/CON-003")
    assert rule.status_code == 200  # reading rules is allowed
    denied = [
        reviewer.patch("/api/v1/scrutiny-rules/CON-003", json={"enabled": False}),
        reviewer.post("/api/v1/scrutiny-rules", json={}),
        reviewer.get("/api/v1/users"),
        reviewer.post("/api/v1/users", json={"username": "x", "display_name": "x", "role": "admin", "password": "p" * 12}),
        reviewer.get("/api/v1/audit-events"),
    ]
    for response in denied:
        assert response.status_code == 403 and response.json()["error"]["code"] == "forbidden"
    assert client.get("/api/v1/scrutiny-rules/CON-003").json()["enabled"] is True
    with app.state.session_factory() as s:
        assert s.execute(select(AuditEvent).where(AuditEvent.action == "authorization.denied")).scalars().first()


def test_admin_user_management(client: TestClient, anon: TestClient) -> None:
    created = client.post("/api/v1/users", json={"username": "carol.review", "display_name": "Carol",
                                                 "role": "reviewer", "password": "long-enough-pw"})
    assert created.status_code == 201 and created.json()["role"] == "reviewer"
    assert client.post("/api/v1/users", json={"username": "carol.review", "display_name": "Carol", "role": "reviewer",
                                              "password": "long-enough-pw"}).status_code == 409
    assert client.post("/api/v1/users", json={"username": "d", "display_name": "D", "role": "reviewer",
                                              "password": "short"}).status_code == 422
    assert client.post("/api/v1/users", json={"username": "evil", "display_name": "E", "role": "superuser",
                                              "password": "long-enough-pw"}).status_code == 422
    promoted = client.patch(f"/api/v1/users/{created.json()['id']}", json={"role": "admin"})
    assert promoted.json()["role"] == "admin"
    me = client.get("/api/v1/auth/me").json()
    assert client.patch(f"/api/v1/users/{me['id']}", json={"role": "reviewer"}).status_code == 409  # no self-lockout
    events = client.get("/api/v1/audit-events", params={"action": "user."}).json()["items"]
    assert {e["action"] for e in events} >= {"user.created", "user.role_changed"}


def test_role_cannot_be_set_through_unrestricted_bodies(reviewer: TestClient) -> None:
    # Role/user ids are never taken from ordinary request bodies.
    r = reviewer.post("/api/v1/auth/login", json={"username": "test.reviewer", "password": TEST_PASSWORD, "role": "admin"})
    assert r.status_code == 422
