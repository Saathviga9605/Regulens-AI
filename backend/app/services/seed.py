"""Deterministic synthetic demonstration data.

All institutions, trusts, addresses and identifiers are invented. Seeded rows carry a
``seed_key``; reseeding skips any key that already exists, so it never duplicates rows and
never modifies records (seeded or user-created). No findings, documents or validation
results are seeded, because those features do not exist yet.
"""

from dataclasses import dataclass, field

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Alert,
    AlertRead,
    EvidenceRequest,
    EvidenceRequestDocument,
    FindingReviewAction,
    Application,
    ApplicationProgramme,
    Document,
    DocumentPage,
    DocumentProcessing,
    ExtractedField,
    Finding,
    IdSequence,
    Institution,
    IssuerReferenceRecord,
    RuleEvaluation,
    ScrutinyRun,
    VerificationAttempt,
)
from app.models.enums import ApplicationStatus as S
from app.models.enums import ApplicationType as T
from app.models.enums import InstitutionType as IT
from app.models.enums import ProgrammeLevel as L
from app.schemas.application import ApplicationCreate, ProgrammeIn
from app.schemas.institution import InstitutionCreate
from app.services import applications as app_service
from app.services import audit
from app.services import institutions as inst_service
from app.services.storage import DocumentStorage

SYN = "(Synthetic)"

INSTITUTIONS: list[tuple[str, dict]] = [
    ("seed-inst-01", dict(name="Deccan Ridge Institute of Engineering", institution_type=IT.PRIVATE_SELF_FINANCING,
                          state="Maharashtra", district="Pune", address="Plot 14, Synthetic Knowledge Park, Hinjewadi Phase 9, Pune 411099",
                          trust_name=f"Deccan Ridge Education Society {SYN}", property_identifier="SYN-MH-PUN-S.No.101/2A")),
    ("seed-inst-02", dict(name="Kaveri Basin College of Technology", institution_type=IT.GOVERNMENT_AIDED,
                          state="Karnataka", district="Mysuru", address="12 Synthetic Ring Road, Hebbal Extension, Mysuru 570099",
                          trust_name=f"Kaveri Basin Vidya Trust {SYN}", property_identifier="SYN-KA-MYS-Sy.No.45/3")),
    ("seed-inst-03", dict(name="Nilgiri Crest Polytechnic", institution_type=IT.GOVERNMENT,
                          state="Tamil Nadu", district="Coimbatore", address="Synthetic Campus Road, Peelamedu North, Coimbatore 641099",
                          trust_name=f"Directorate of Technical Education (Demo) {SYN}", property_identifier="SYN-TN-CBE-SF.No.221")),
    ("seed-inst-04", dict(name="Gomti Valley Institute of Management", institution_type=IT.PRIVATE_SELF_FINANCING,
                          state="Uttar Pradesh", district="Lucknow", address="Sector 99, Synthetic Shiksha Nagar, Lucknow 226099",
                          trust_name=f"Gomti Valley Shiksha Samiti {SYN}", property_identifier="SYN-UP-LKO-Khasra.778")),
    ("seed-inst-05", dict(name="Hooghly Riverside Engineering College", institution_type=IT.PRIVATE_SELF_FINANCING,
                          state="West Bengal", district="Hooghly", address="7 Synthetic Strand Lane, Serampore North, Hooghly 712299",
                          trust_name=f"Riverside Technical Education Foundation {SYN}", property_identifier="SYN-WB-HGY-Dag.No.312")),
    ("seed-inst-06", dict(name="Narmada Plains Institute of Pharmacy", institution_type=IT.DEEMED_UNIVERSITY,
                          state="Gujarat", district="Vadodara", address="Synthetic Science Avenue, Gotri West, Vadodara 390099",
                          trust_name=f"Narmada Plains Pharmaceutical Education Trust {SYN}", property_identifier="SYN-GJ-VAD-RS.No.64/1")),
    ("seed-inst-07", dict(name="Godavari Bend Institute of Technology", institution_type=IT.STATE_PRIVATE_UNIVERSITY,
                          state="Telangana", district="Warangal", address="Survey Hill Road, Synthetic Tech Township, Warangal 506099",
                          trust_name=f"Godavari Bend Educational Academy {SYN}", property_identifier="SYN-TS-WGL-Sy.No.512/B")),
    ("seed-inst-08", dict(name="Aravalli Foothills College of Engineering", institution_type=IT.PRIVATE_SELF_FINANCING,
                          state="Rajasthan", district="Jaipur", address="Synthetic Industrial Area, Sitapura Extension, Jaipur 302099",
                          trust_name=f"Aravalli Foothills Shiksha Parishad {SYN}", property_identifier="SYN-RJ-JPR-Khasra.1190")),
]


def _p(level: L, course: str, existing: int, proposed: int) -> ProgrammeIn:
    return ProgrammeIn(programme_level=level, course_name=course, existing_intake=existing, proposed_intake=proposed)


# Status paths are applied through the real workflow service, so seeded statuses are reachable states.
_READY = [S.READY_FOR_PRELIMINARY_SCRUTINY]
_UNDER = _READY + [S.UNDER_PRELIMINARY_SCRUTINY]
_AWAIT = _UNDER + [S.AWAITING_ADDITIONAL_EVIDENCE]
_DONE = _UNDER + [S.PRELIMINARY_SCRUTINY_COMPLETED]

APPLICATIONS: list[tuple[str, str, str, T, list[ProgrammeIn], list[S]]] = [
    ("seed-app-01", "seed-inst-01", "2026-27", T.EOA_NO_CHANGE,
     [_p(L.UNDERGRADUATE, "B.Tech Computer Science and Engineering", 120, 120),
      _p(L.UNDERGRADUATE, "B.Tech Mechanical Engineering", 60, 60)], []),
    ("seed-app-02", "seed-inst-01", "2025-26", T.INCREASE_IN_INTAKE,
     [_p(L.UNDERGRADUATE, "B.Tech Computer Science and Engineering", 60, 120)], _DONE),
    ("seed-app-03", "seed-inst-02", "2026-27", T.INTRODUCTION_OF_NEW_COURSE,
     [_p(L.UNDERGRADUATE, "B.E. Electronics and Communication Engineering", 120, 120),
      _p(L.UNDERGRADUATE, "B.E. Artificial Intelligence and Data Science", 0, 60)], _READY),
    ("seed-app-04", "seed-inst-03", "2026-27", T.EOA_NO_CHANGE,
     [_p(L.DIPLOMA, "Diploma in Civil Engineering", 60, 60),
      _p(L.DIPLOMA, "Diploma in Electrical and Electronics Engineering", 60, 60)], _UNDER),
    ("seed-app-05", "seed-inst-04", "2026-27", T.REDUCTION_IN_INTAKE,
     [_p(L.POSTGRADUATE, "MBA", 180, 120)], _AWAIT),
    ("seed-app-06", "seed-inst-05", "2026-27", T.INCREASE_IN_INTAKE,
     [_p(L.UNDERGRADUATE, "B.Tech Information Technology", 60, 90),
      _p(L.UNDERGRADUATE, "B.Tech Civil Engineering", 60, 60)], []),
    ("seed-app-07", "seed-inst-06", "2026-27", T.EOA_NO_CHANGE,
     [_p(L.UNDERGRADUATE, "B.Pharm", 100, 100), _p(L.POSTGRADUATE, "M.Pharm Pharmaceutics", 15, 15)], _UNDER),
    ("seed-app-08", "seed-inst-07", "2026-27", T.CHANGE_OF_INSTITUTION_NAME,
     [_p(L.UNDERGRADUATE, "B.Tech Electrical Engineering", 60, 60)], _READY),
    ("seed-app-09", "seed-inst-08", "2026-27", T.INTRODUCTION_OF_NEW_COURSE,
     [_p(L.UNDERGRADUATE, "B.Tech Computer Science and Engineering", 180, 180),
      _p(L.POSTGRADUATE, "M.Tech Cyber Security", 0, 18)], []),
    ("seed-app-10", "seed-inst-08", "2025-26", T.EOA_NO_CHANGE,
     [_p(L.UNDERGRADUATE, "B.Tech Computer Science and Engineering", 180, 180)], _DONE),
    ("seed-app-11", "seed-inst-02", "2025-26", T.REDUCTION_IN_INTAKE,
     [_p(L.UNDERGRADUATE, "B.E. Mechanical Engineering", 120, 60)], _AWAIT),
    ("seed-app-12", "seed-inst-05", "2027-28", T.EOA_NO_CHANGE,
     [_p(L.UNDERGRADUATE, "B.Tech Information Technology", 90, 90)], []),
]


@dataclass
class SeedResult:
    institutions_created: int = 0
    institutions_skipped: int = 0
    applications_created: int = 0
    applications_skipped: int = 0
    created_codes: list[str] = field(default_factory=list)


def seed(session: Session) -> SeedResult:
    result = SeedResult()
    codes: dict[str, str] = {}
    for key, values in INSTITUTIONS:
        existing = session.execute(select(Institution).where(Institution.seed_key == key)).scalar_one_or_none()
        if existing is not None:
            result.institutions_skipped += 1
            codes[key] = existing.institution_code
            continue
        inst = inst_service.create_institution(session, InstitutionCreate(**values), seed_key=key)
        codes[key] = inst.institution_code
        result.institutions_created += 1
        result.created_codes.append(inst.institution_code)

    for key, inst_key, year, app_type, programmes, path in APPLICATIONS:
        if session.execute(select(Application.id).where(Application.seed_key == key)).first() is not None:
            result.applications_skipped += 1
            continue
        app = app_service.create_application(
            session,
            ApplicationCreate(institution_code=codes[inst_key], academic_year=year,
                              application_type=app_type, programmes=programmes),
            seed_key=key,
        )
        for target in path:
            app_service.change_status(session, app.application_code, target)
        result.applications_created += 1
        result.created_codes.append(app.application_code)
    return result


def summary(session: Session) -> dict:
    def count(model, *where) -> int:
        return session.execute(select(func.count()).select_from(model).where(*where)).scalar_one()

    by_status = dict(session.execute(select(Application.status, func.count()).group_by(Application.status)).all())
    return {
        "institutions_total": count(Institution),
        "institutions_seeded": count(Institution, Institution.seed_key.is_not(None)),
        "applications_total": count(Application),
        "applications_seeded": count(Application, Application.seed_key.is_not(None)),
        "applications_by_status": {s.value: by_status.get(s, 0) for s in S},
        "documents_total": count(Document),
        "documents_seeded": count(Document, Document.seed_key.is_not(None)),
        "synthetic_issuer_references": count(IssuerReferenceRecord),
        "scrutiny_runs": count(ScrutinyRun),
    }


class ResetRefused(Exception):
    pass


def reset_data(session: Session, settings: Settings, *, confirm: bool) -> int:
    """Delete ALL institution, application, document, processing, scrutiny, review, evidence-request, alert and
    synthetic issuer-reference rows
    (user-created included) and the stored files those document rows reference. Scrutiny rules and the schema
    are kept. Returns the number of stored files removed.

    Requires ``confirm=True`` and a development/test environment. Never called at startup or by tests
    against a developer database.
    """
    if not confirm:
        raise ResetRefused(
            "Refusing to reset: pass --confirm-reset to delete all institution, application and document data."
        )
    if settings.environment not in ("development", "test"):
        raise ResetRefused(f"Refusing to reset in the '{settings.environment}' environment.")
    keys = [k for k in session.execute(select(Document.storage_key)).scalars() if k]
    session.execute(update(Document).values(duplicate_of_id=None))
    for model in (AlertRead, Alert, EvidenceRequestDocument, EvidenceRequest, FindingReviewAction,
                  VerificationAttempt, Finding, RuleEvaluation, ScrutinyRun, ExtractedField, DocumentPage,
                  DocumentProcessing, Document, ApplicationProgramme, Application, Institution, IdSequence,
                  IssuerReferenceRecord):
        session.execute(delete(model))
    # The audit log, users and scrutiny rules are kept; the reset itself is audited.
    audit.record(session, "data.reset", "database", None, details={"stored_files": len(keys)})
    session.commit()
    # Remove files only after the commit, and only those referenced by the deleted rows.
    storage = DocumentStorage(settings.document_storage_path)
    removed = 0
    for key in keys:
        path = storage.open_path(key)
        if path is not None:
            DocumentStorage.discard(path)
            removed += 1
    return removed
