"""Alembic environment.

Invoked by ``app.db.init_db.run_migrations`` (app startup / CLI) with a live connection
in ``config.attributes["connection"]``, or by the ``alembic`` CLI using app settings.
"""

from alembic import context
from sqlalchemy import Connection

import app.models  # noqa: F401  (populate metadata for autogenerate)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_engine

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE operations
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    engine = build_engine(get_settings())
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()
