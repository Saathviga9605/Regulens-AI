"""Health checks against real dependencies."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger("regulens.health")


def check_database(session: Session) -> tuple[bool, str | None]:
    """Run a lightweight query. Returns (healthy, client-safe detail)."""
    try:
        healthy = session.execute(text("SELECT 1")).scalar_one() == 1
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("Database health check failed", extra={"error_type": type(exc).__name__})
        return False, "Database connectivity check failed."
    return healthy, None if healthy else "Unexpected database response."
