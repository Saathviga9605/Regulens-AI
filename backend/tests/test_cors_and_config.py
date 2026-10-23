from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT
from tests.conftest import TEST_ORIGIN, make_settings


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={"Origin": TEST_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == TEST_ORIGIN

    simple = client.get("/api/v1/health", headers={"Origin": TEST_ORIGIN})
    assert simple.headers["access-control-allow-origin"] == TEST_ORIGIN


def test_cors_rejects_unlisted_origin(client: TestClient) -> None:
    evil = "http://evil.example.com"
    preflight = client.options(
        "/api/v1/health",
        headers={"Origin": evil, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers

    simple = client.get("/api/v1/health", headers={"Origin": evil})
    assert "access-control-allow-origin" not in simple.headers


def test_wildcard_cors_rejected_in_production(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "x.db", environment="production", cors_origins="*")
    with pytest.raises(ValueError):
        _ = settings.cors_origin_list


def test_relative_sqlite_path_resolves_under_repo_root(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "x.db", database_url="sqlite:///data/regulens.db")
    assert settings.sqlite_path == (REPO_ROOT / "data" / "regulens.db").resolve()
