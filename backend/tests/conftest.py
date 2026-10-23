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
