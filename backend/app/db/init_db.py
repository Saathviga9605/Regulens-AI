"""Database initialisation via Alembic migrations.

``init_db`` upgrades the schema to the latest revision. It is non-destructive: migrations
only add or alter structures, and existing rows are preserved. ``create_all`` is no longer
used because it cannot evolve an existing schema.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

logger = logging.getLogger("regulens.db")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS_DIR.as_posix())
    return config


def run_migrations(engine: Engine, revision: str = "head") -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def init_db(engine: Engine) -> None:
    run_migrations(engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database initialised")
