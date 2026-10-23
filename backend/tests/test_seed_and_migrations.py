import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app import cli
from app.db.init_db import init_db
from app.db.session import build_engine, build_session_factory
from app.main import create_app
from app.services import seed as seed_service
from tests.conftest import application_payload, institution_payload, make_settings


@pytest.fixture
def seeded_env(tmp_path: Path):
    settings = make_settings(tmp_path / "seed.db")
    engine = build_engine(settings)
    init_db(engine)
    factory = build_session_factory(engine)
    yield settings, engine, factory
    engine.dispose()


def test_seed_counts(seeded_env) -> None:
    _, _, factory = seeded_env
    with factory() as session:
        result = seed_service.seed(session)
        summary = seed_service.summary(session)
    assert (result.institutions_created, result.applications_created) == (8, 12)
    assert summary["institutions_total"] == 8
    assert summary["applications_total"] == 12
    assert all(count >= 2 for count in summary["applications_by_status"].values())


def test_seed_data_is_varied_and_synthetic(seeded_env) -> None:
    from app.models import Application, Institution

    _, _, factory = seeded_env
    with factory() as session:
        seed_service.seed(session)
        institutions = session.query(Institution).all()
        applications = session.query(Application).all()
        assert len({i.state for i in institutions}) == 8
        assert all("(Synthetic)" in i.trust_name and i.property_identifier.startswith("SYN-") for i in institutions)
        assert len({a.application_type for a in applications}) == 5
        assert len({a.academic_year for a in applications}) >= 3


def test_reseed_is_idempotent_and_preserves_user_records(seeded_env) -> None:
    settings, _, factory = seeded_env
    with factory() as session:
        seed_service.seed(session)

    app = create_app(settings)
    with TestClient(app) as client:
        inst = client.post("/api/v1/institutions", json=institution_payload(name="User Created Synthetic")).json()
        user_app = client.post("/api/v1/applications", json=application_payload(inst["institution_code"])).json()
        # A user edit to a seeded institution must survive reseeding.
        seeded_code = client.get("/api/v1/institutions", params={"q": "deccan"}).json()["items"][0]["institution_code"]
        client.patch(f"/api/v1/institutions/{seeded_code}", json={"name": "Deccan Ridge Edited By User"})

    with factory() as session:
        for _ in range(2):
            again = seed_service.seed(session)
            assert (again.institutions_created, again.applications_created) == (0, 0)
            assert (again.institutions_skipped, again.applications_skipped) == (8, 12)
        summary = seed_service.summary(session)
    assert summary["institutions_total"] == 9 and summary["applications_total"] == 13

    with TestClient(app) as client:
        assert client.get(f"/api/v1/institutions/{seeded_code}").json()["name"] == "Deccan Ridge Edited By User"
        assert client.get(f"/api/v1/applications/{user_app['application_code']}").json() == user_app


def test_reset_requires_confirmation_and_safe_environment(seeded_env, tmp_path: Path) -> None:
    settings, _, factory = seeded_env
    with factory() as session:
        seed_service.seed(session)
        with pytest.raises(seed_service.ResetRefused):
            seed_service.reset_data(session, settings, confirm=False)
        prod = make_settings(tmp_path / "seed.db", environment="production")
        with pytest.raises(seed_service.ResetRefused):
            seed_service.reset_data(session, prod, confirm=True)
        assert seed_service.summary(session)["applications_total"] == 12
        seed_service.reset_data(session, settings, confirm=True)
        assert seed_service.summary(session)["applications_total"] == 0


def test_cli_reset_without_flag_refuses(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "cli.db"
    monkeypatch.setattr(cli, "get_settings", lambda: make_settings(db))
    assert cli.main(["seed"]) == 0
    assert cli.main(["reset-data"]) == 2
    assert "--confirm-reset" in capsys.readouterr().err
    assert cli.main(["seed-summary"]) == 0
    assert '"applications_total": 12' in capsys.readouterr().out


def test_migrations_create_schema_on_fresh_database(seeded_env) -> None:
    _, engine, _ = seeded_env
    tables = set(inspect(engine).get_table_names())
    assert {"institutions", "applications", "application_programmes", "id_sequences", "alembic_version"} <= tables


def test_migrations_preserve_existing_data_and_are_repeatable(tmp_path: Path) -> None:
    db = tmp_path / "existing.db"
    # Simulate a pre-existing Deliverable-1 database holding unrelated data.
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE local_notes (id INTEGER PRIMARY KEY, text TEXT)")
        conn.execute("INSERT INTO local_notes (text) VALUES ('keep me')")

    settings = make_settings(db)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        inst = client.post("/api/v1/institutions", json=institution_payload()).json()
    with TestClient(create_app(settings)) as client:  # second startup re-runs migrations: no-op
        assert client.get(f"/api/v1/institutions/{inst['institution_code']}").status_code == 200

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT text FROM local_notes").fetchall() == [("keep me",)]
        assert conn.execute("SELECT version_num FROM alembic_version").fetchall() == [("0003",)]
