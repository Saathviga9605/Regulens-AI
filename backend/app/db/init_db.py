"""Minimal database initialisation.

Creates tables for any models registered on ``Base.metadata`` and verifies the
connection. No business tables exist yet; Alembic migrations are planned once
real models are introduced.
"""

import logging

from sqlalchemy import Engine, text

import app.models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base

logger = logging.getLogger("regulens.db")


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database initialised")
