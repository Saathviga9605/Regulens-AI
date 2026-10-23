"""Developer commands. Run from backend/:  python -m app.cli <command>

  migrate                     Upgrade the database schema to the latest migration.
  seed                        Insert the synthetic demo dataset (idempotent).
  seed-summary                Print record counts.
  reset-data --confirm-reset  DELETE all institution/application data (development/test only).
"""

import argparse
import json
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import run_migrations
from app.db.session import build_engine, build_session_factory
from app.services import seed as seed_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ReguLens AI developer commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations")
    sub.add_parser("seed", help="Insert synthetic demo data (idempotent)")
    sub.add_parser("seed-summary", help="Show record counts")
    reset = sub.add_parser("reset-data", help="Delete ALL institution and application data")
    reset.add_argument("--confirm-reset", action="store_true", help="Required: confirms the destructive reset")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging("WARNING")
    engine = build_engine(settings)
    try:
        run_migrations(engine)
        factory = build_session_factory(engine)
        with factory() as session:
            if args.command == "migrate":
                print("Database schema is up to date.")
            elif args.command == "seed":
                result = seed_service.seed(session)
                print(f"Institutions: {result.institutions_created} created, {result.institutions_skipped} already present")
                print(f"Applications: {result.applications_created} created, {result.applications_skipped} already present")
                print(json.dumps(seed_service.summary(session), indent=2))
            elif args.command == "seed-summary":
                print(json.dumps(seed_service.summary(session), indent=2))
            elif args.command == "reset-data":
                try:
                    seed_service.reset_data(session, settings, confirm=args.confirm_reset)
                except seed_service.ResetRefused as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                print("All institution and application data deleted.")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
