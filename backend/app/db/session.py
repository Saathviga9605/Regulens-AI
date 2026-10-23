"""SQLAlchemy engine and session management."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    is_sqlite = settings.database_backend == "sqlite"
    # timeout: wait for SQLite's write lock instead of failing immediately under concurrent writes.
    connect_args: dict = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    path = settings.sqlite_path
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session, rolling back on error and always closing it."""
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
