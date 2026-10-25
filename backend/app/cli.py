"""Developer commands. Run from backend/:  python -m app.cli <command>

  migrate                     Upgrade the database schema to the latest migration.
  seed                        Insert the synthetic demo dataset incl. demo PDFs and synthetic issuer
                              reference records (idempotent; never modifies existing records).
  seed-summary                Print record counts.
  create-demo-users           Create or reconcile the LOCAL DEMO accounts from REGULENS_DEMO_* settings
                              (idempotent; refused in production or when REGULENS_DEMO_USERS_ENABLED=false).
  create-user --username U --role reviewer|admin [--display-name N]
                              Password read from REGULENS_NEW_USER_PASSWORD or an interactive prompt.
  reset-data --confirm-reset  DELETE all institution/application/document data and stored files (development/test only).
  reuse-fixtures --load       Add the four fictional cross-case reuse demo cases (idempotent; never modifies data).
  reuse-fixtures --reset --confirm-reset
                              Delete ONLY the reuse fixture cases (development/test only).
  reuse-scan --application CODE
                              Run the cross-case reuse scan for one application (as the system actor).
  grant-cross-case --username U [--revoke]
                              Grant or revoke the cross-case reviewer permission (audited).
  reuse-eval [--out DIR]      Run the A0/A1/A4 evaluation on the synthetic fixtures; writes metrics.json,
                              metrics.csv and summary.md (no database or network needed).
"""

import argparse
import getpass
import json
import os
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.init_db import run_migrations
from app.db.session import build_engine, build_session_factory
from app.core.errors import AppError
from app.models.enums import UserRole
from app.services import auth, demo_documents, rule_catalog
from app.services import seed as seed_service
from app.services.storage import DocumentStorage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ReguLens AI developer commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations")
    sub.add_parser("seed", help="Insert synthetic demo data (idempotent)")
    sub.add_parser("seed-summary", help="Show record counts")
    sub.add_parser("create-demo-users", help="Create fictional demo reviewer/admin accounts")
    cu = sub.add_parser("create-user", help="Create a user")
    cu.add_argument("--username", required=True)
    cu.add_argument("--role", required=True, choices=["reviewer", "admin"])
    cu.add_argument("--display-name", default=None)
    reset = sub.add_parser("reset-data", help="Delete ALL institution, application and document data")
    reset.add_argument("--confirm-reset", action="store_true", help="Required: confirms the destructive reset")
    rf = sub.add_parser("reuse-fixtures", help="Load or reset the cross-case reuse demo cases")
    rf_mode = rf.add_mutually_exclusive_group(required=True)
    rf_mode.add_argument("--load", action="store_true")
    rf_mode.add_argument("--reset", action="store_true")
    rf.add_argument("--confirm-reset", action="store_true", help="Required with --reset")
    rs = sub.add_parser("reuse-scan", help="Run the cross-case reuse scan for one application")
    rs.add_argument("--application", required=True)
    gc = sub.add_parser("grant-cross-case", help="Grant or revoke the cross-case reviewer permission")
    gc.add_argument("--username", required=True)
    gc.add_argument("--revoke", action="store_true")
    re_ = sub.add_parser("reuse-eval", help="Run the A0/A1/A4 evaluation on synthetic fixtures")
    re_.add_argument("--out", default=None, help="Directory for metrics.json, metrics.csv and summary.md")
    re_.add_argument("--no-ocr", action="store_true", help="Evaluate without OCR (to measure its contribution)")
    args = parser.parse_args(argv)

    if args.command == "reuse-eval":
        return _reuse_eval(args.out, use_ocr=not args.no_ocr)

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
                if settings.environment != "production" and settings.demo_users_enabled:
                    _demo_users(session, settings)
                else:
                    print("Demo accounts: skipped (production or REGULENS_DEMO_USERS_ENABLED=false).")
                print(json.dumps(seed_service.summary(session), indent=2))
            elif args.command == "create-demo-users":
                return _demo_users(session, settings)
            elif args.command == "create-user":
                password = os.environ.get("REGULENS_NEW_USER_PASSWORD") or getpass.getpass("Password: ")
                try:
                    user = auth.create_user(session, username=args.username, role=UserRole(args.role),
                                            display_name=args.display_name or args.username, password=password)
                except AppError as exc:
                    print(exc.message, file=sys.stderr)
                    return 2
                print(f"Created {user.role.value} '{user.username}'.")
            elif args.command == "seed-summary":
                print(json.dumps(seed_service.summary(session), indent=2))
            elif args.command == "reset-data":
                try:
                    removed = seed_service.reset_data(session, settings, confirm=args.confirm_reset)
                except seed_service.ResetRefused as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                print(f"All institution, application and document data deleted ({removed} stored files removed).")
            elif args.command == "reuse-fixtures":
                from app.services import reuse_fixtures

                if args.load:
                    storage = DocumentStorage(settings.document_storage_path)
                    storage.ensure_dirs()
                    res = reuse_fixtures.load(session, storage, settings.max_upload_bytes)
                    print(f"Reuse fixtures: {len(res.created)} created, {len(res.skipped)} documents already present")
                    for key, code in res.application_codes.items():
                        print(f"  {key}: {code}")
                else:
                    try:
                        removed = reuse_fixtures.reset(session, settings, confirm=args.confirm_reset)
                    except reuse_fixtures.FixtureResetRefused as exc:
                        print(str(exc), file=sys.stderr)
                        return 2
                    print(f"Reuse fixture cases deleted ({removed} stored files removed). Other data untouched.")
            elif args.command == "reuse-scan":
                from app.core.context import SYSTEM_ACTOR
                from app.services import reuse
                from app.services.ocr import build_ocr_engine

                storage = DocumentStorage(settings.document_storage_path)
                try:
                    run = reuse.run_scan(session, storage, settings, build_ocr_engine(settings),
                                         args.application, SYSTEM_ACTOR)
                except AppError as exc:
                    print(exc.message, file=sys.stderr)
                    return 2
                print(json.dumps({"run_id": run.id, "status": run.status.value, "documents_scanned": run.documents_scanned,
                                  "comparisons": run.comparisons, "candidates": run.candidates,
                                  "pairs_created": run.pairs_created, "pairs_reused": run.pairs_reused,
                                  "outcomes": run.outcome_counts}, indent=2))
            elif args.command == "grant-cross-case":
                from sqlalchemy import select

                from app.core.context import SYSTEM_ACTOR
                from app.models import User

                user = session.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
                if user is None:
                    print(f"No user '{args.username}'.", file=sys.stderr)
                    return 2
                auth.update_user(session, user.id, SYSTEM_ACTOR, cross_case_reviewer=not args.revoke)
                print(f"Cross-case reviewer permission {'revoked from' if args.revoke else 'granted to'} '{user.username}'.")
    finally:
        engine.dispose()
    return 0


def _reuse_eval(out: str | None, use_ocr: bool = True) -> int:
    from pathlib import Path

    from app.core.config import get_settings as _settings
    from app.services.ocr import build_ocr_engine
    from app.services.reuse_eval import evaluate

    result = evaluate(ocr=build_ocr_engine(_settings()) if use_ocr else None)
    if out:
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        (target / "metrics.json").write_text(json.dumps(result.data, indent=2, default=str), encoding="utf-8")
        (target / "metrics.csv").write_text(result.to_csv(), encoding="utf-8")
        (target / "summary.md").write_text(result.to_markdown(), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # legacy Windows consoles cannot encode every character
    print(result.to_markdown())
    if out:
        print(f"Wrote metrics.json, metrics.csv and summary.md to {target}")
    return 0


def _demo_users(session, settings) -> int:
    try:
        results = auth.bootstrap_demo_users(session, settings)
    except auth.DemoBootstrapRefused as exc:
        print(f"Demo accounts not bootstrapped: {exc}", file=sys.stderr)
        return 2
    for username, result in results:
        print(f"Demo account '{username}': {result}  (LOCAL DEMO ONLY - CHANGE BEFORE SHARING)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
