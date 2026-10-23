from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import create_app
from tests.conftest import make_settings


def test_health_returns_expected_structure(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "app_name": "ReguLens AI",
        "api_version": "v1",
        "status": "ok",
        "database": {"status": "ok", "detail": None},
    }
    assert response.headers.get("X-Request-ID")


def test_health_executes_real_database_query(app, client: TestClient) -> None:
    statements: list[str] = []

    @event.listens_for(app.state.engine, "before_cursor_execute")
    def capture(conn, cursor, statement, *args):
        statements.append(statement)

    client.get("/api/v1/health")
    assert any("SELECT 1" in s for s in statements)


def test_health_creates_database_file_in_configured_location(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "regulens.db"
    with TestClient(create_app(make_settings(db_path))) as c:
        assert c.get("/api/v1/health").json()["database"]["status"] == "ok"
    assert db_path.exists()


def test_health_reports_degraded_when_database_unreachable(tmp_path: Path) -> None:
    # A directory cannot be opened as a SQLite file, so the real query fails.
    unopenable = tmp_path / "is_a_directory"
    unopenable.mkdir()
    with TestClient(create_app(make_settings(unopenable)), raise_server_exceptions=False) as c:
        response = c.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "unavailable"
    assert body["database"]["detail"] == "Database connectivity check failed."
    assert str(tmp_path) not in response.text
    assert tmp_path.as_posix() not in response.text
