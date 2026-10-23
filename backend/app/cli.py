"""Developer commands. Run from backend/:  python -m app.cli <command>

  migrate                     Upgrade the database schema to the latest migration.
  seed                        Insert the synthetic demo dataset incl. demo PDFs and synthetic issuer
                              reference records (idempotent; never modifies existing records).
  seed-summary                Print record counts.
  reset-data --confirm-reset  DELETE all institution/application/document data and stored files (development/test only).
"""

import argparse
import json
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import run_migrations
from app.db.session import build_engine, build_session_factory
from app.services import demo_documents, rule_catalog
from app.services import seed as seed_service
from app.services.storage import DocumentStorage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ReguLens AI developer commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations")
    sub.add_parser("seed", help="Insert synthetic demo data (idempotent)")
    sub.add_parser("seed-summary", help="Show record counts")
    reset = sub.add_parser("reset-data", help="Delete ALL institution, application and document data")
    reset.add_argument("--confirm-reset", action="store_true", help="Required: confirms the destructive reset")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging("WARNING")
    engine = build_engine(settings)
    try:
        run_migrations(engine)
        factory = build_session_factory(engine)
        with factory() as session:
            rule_catalog.ensure_default_rules(session)
            if args.command == "migrate":
                print("Database schema is up to date.")
            elif args.command == "seed":
                result = seed_service.seed(session)
                print(f"Institutions: {result.institutions_created} created, {result.institutions_skipped} already present")
                print(f"Applications: {result.applications_created} created, {result.applications_skipped} already present")
                storage = DocumentStorage(settings.document_storage_path)
                storage.ensure_dirs()
                demo = demo_documents.seed_demo_documents(session, storage, settings.max_upload_bytes)
                print(f"Demo documents: {demo.documents_created} created, {demo.documents_skipped} already present")
                print(f"Synthetic issuer reference records: {demo.references_created} created")
                for note in demo.notes:
                    print(f"  note: {note}")
                print(json.dumps(seed_service.summary(session), indent=2))
            elif args.command == "seed-summary":
                print(json.dumps(seed_service.summary(session), indent=2))
            elif args.command == "reset-data":
                try:
                    removed = seed_service.reset_data(session, settings, confirm=args.confirm_reset)
                except seed_service.ResetRefused as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                print(f"All institution, application and document data deleted ({removed} stored files removed).")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
