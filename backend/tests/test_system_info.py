from fastapi.testclient import TestClient


def test_system_info_returns_safe_metadata(client: TestClient, settings) -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "app_name",
        "app_version",
        "api_version",
        "environment",
        "database_backend",
        "implemented_capabilities",
        "planned_capabilities",
    }
    assert body["environment"] == "test"
    assert body["database_backend"] == "sqlite"
    assert body["planned_capabilities"]

    text = response.text.lower()
    assert settings.database_url.lower() not in text
    assert str(settings.sqlite_path).lower() not in text
    for forbidden in ("secret", "password", "token", "sqlite:///"):
        assert forbidden not in text
