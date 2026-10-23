"""Test fixtures. Every test app uses an isolated temporary SQLite database."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Ensure importing app.main never points at the developer's local database.
os.environ["REGULENS_ENVIRONMENT"] = "test"
os.environ["REGULENS_DATABASE_URL"] = "sqlite:///:memory:"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_ORIGIN = "http://localhost:5173"


def make_settings(db_path: Path, **overrides) -> Settings:
    values = {
        "environment": "test",
        "database_url": f"sqlite:///{db_path.as_posix()}",
        # Each test database gets its own private storage directory next to it.
        "document_storage_dir": str(db_path.parent / f"{db_path.stem}-documents"),
        "cors_origins": TEST_ORIGIN,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path / "test.db")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def institution_payload(**overrides) -> dict:
    payload = {
        "name": "Test Synthetic Institute of Technology",
        "institution_type": "private_self_financing",
        "state": "Kerala",
        "district": "Ernakulam",
        "address": "1 Synthetic Test Road, Kochi 682099",
        "trust_name": "Test Synthetic Education Trust",
        "property_identifier": "SYN-TEST-001",
    }
    payload.update(overrides)
    return payload


def application_payload(institution_code: str, **overrides) -> dict:
    payload = {
        "institution_code": institution_code,
        "academic_year": "2026-27",
        "application_type": "eoa_no_change",
        "programmes": [
            {"programme_level": "undergraduate", "course_name": "B.Tech Civil Engineering",
             "existing_intake": 60, "proposed_intake": 60},
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def institution(client: TestClient) -> dict:
    response = client.post("/api/v1/institutions", json=institution_payload())
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def draft(client: TestClient, institution: dict) -> dict:
    response = client.post("/api/v1/applications", json=application_payload(institution["institution_code"]))
    assert response.status_code == 201, response.text
    return response.json()
