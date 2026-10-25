"""Load the cross-case reuse demonstration fixtures into the database (fictional cases only).

``load`` creates four fictional institutions with one draft application each and uploads documents from the
held-out evaluation split through the normal intake path:

* Case A — source structural stability certificate (``ho_ssc_src``).
* Case B — a different institution submitting a rescaled vector copy of A's certificate (``ho_ssc_vec``):
  the transformed positive pair.
* Case C — a different institution submitting a scan-like raster copy (``ho_ssc_scan``): image-only, no OCR text.
* Case D — the same issuer template with different institution, number and dates (``ho_ssc_tmpl``): the hard
  negative.

Idempotent through ``seed_key`` values prefixed ``reuse-``; existing rows are never modified. ``reset`` deletes
only rows carrying those keys (and records that depend on them), requires explicit confirmation and refuses
outside development/test. It never touches user-created data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import (
    Alert,
    AlertRead,
    Application,
    ApplicationProgramme,
    CasePair,
    Document,
    DocumentFingerprint,
    DocumentPage,
    DocumentProcessing,
    EvidenceRequest,
    EvidenceRequestDocument,
    ExtractedField,
    Finding,
    FindingReviewAction,
    Institution,
    ReuseScanRun,
    RuleEvaluation,
    ScrutinyRun,
    VerificationAttempt,
)
from app.models.enums import ApplicationType as T
from app.models.enums import DocumentCategory
from app.models.enums import InstitutionType as IT
from app.models.enums import ProgrammeLevel as L
from app.schemas.application import ApplicationCreate, ProgrammeIn
from app.schemas.institution import InstitutionCreate
from app.services import applications as app_service
from app.services import audit
from app.services import documents as document_service
from app.services import institutions as inst_service
from app.services.reuse_dataset import build_dataset
from app.services.storage import DocumentStorage

PREFIX = "reuse-"
SYN = "(Synthetic)"

CASES = [
    ("reuse-inst-a", "reuse-app-a", "reuse-doc-a", "ho_ssc_src", "structural-stability-certificate.pdf",
     dict(name="Konkan Coast Institute of Engineering", institution_type=IT.PRIVATE_SELF_FINANCING, state="Maharashtra",
          district="Ratnagiri", address="88 Synthetic Harbour Road, Ratnagiri South 415699",
          trust_name=f"Konkan Coast Education Trust {SYN}", property_identifier="SYN-MH-RTN-S.No.77/1")),
    ("reuse-inst-b", "reuse-app-b", "reuse-doc-b", "ho_ssc_vec", "stability-cert-scaled.pdf",
     dict(name="Malvan Bay Institute of Technology", institution_type=IT.PRIVATE_SELF_FINANCING, state="Maharashtra",
          district="Sindhudurg", address="5 Synthetic Jetty Road, Malvan 416699",
          trust_name=f"Malvan Bay Vidya Samiti {SYN}", property_identifier="SYN-MH-SDG-S.No.12/4")),
    ("reuse-inst-c", "reuse-app-c", "reuse-doc-c", "ho_ssc_scan", "structural-certificate-scan.pdf",
     dict(name="Dapoli Hills Polytechnic", institution_type=IT.GOVERNMENT_AIDED, state="Maharashtra",
          district="Ratnagiri", address="21 Synthetic Ridge Lane, Dapoli 415799",
          trust_name=f"Dapoli Hills Shikshan Mandal {SYN}", property_identifier="SYN-MH-RTN-S.No.140/2")),
    ("reuse-inst-d", "reuse-app-d", "reuse-doc-d", "ho_ssc_tmpl", "structural-stability-2025.pdf",
     dict(name="Sahyadri Heights College of Technology", institution_type=IT.PRIVATE_SELF_FINANCING, state="Maharashtra",
          district="Ratnagiri", address="3 Synthetic Ghat Lane, Chiplun West 415699",
          trust_name=f"Sahyadri Heights Education Society {SYN}", property_identifier="SYN-MH-RTN-S.No.9/7")),
]


@dataclass
class FixtureResult:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    application_codes: dict[str, str] = field(default_factory=dict)


def load(session: Session, storage: DocumentStorage, max_upload_bytes: int) -> FixtureResult:
    ds = build_dataset()
    result = FixtureResult()
    for inst_key, app_key, doc_key, fixture_key, filename, values in CASES:
        inst = session.execute(select(Institution).where(Institution.seed_key == inst_key)).scalar_one_or_none()
        if inst is None:
            inst = inst_service.create_institution(session, InstitutionCreate(**values), seed_key=inst_key)
            result.created.append(inst.institution_code)
        app = session.execute(select(Application).where(Application.seed_key == app_key)).scalar_one_or_none()
        if app is None:
            app = app_service.create_application(session, ApplicationCreate(
                institution_code=inst.institution_code, academic_year="2026-27", application_type=T.EOA_NO_CHANGE,
                programmes=[ProgrammeIn(programme_level=L.UNDERGRADUATE, course_name="B.Tech Civil Engineering",
                                        existing_intake=60, proposed_intake=60)]), seed_key=app_key)
            result.created.append(app.application_code)
        result.application_codes[app_key] = app.application_code
        if session.execute(select(Document.id).where(Document.seed_key == doc_key)).first():
            result.skipped.append(doc_key)
            continue
        content = ds.docs[fixture_key].pdf
        if len(content) > max_upload_bytes:
            raise AppError(413, "fixture_too_large", f"Fixture {fixture_key} exceeds the upload limit.")
        temp = storage.new_temp_path()
        temp.write_bytes(content)
        received = document_service.ReceivedFile(temp, len(content), hashlib.sha256(content).hexdigest())
        document_service.store_document(session, storage, application_code=app.application_code, received=received,
                                        filename=filename, category=DocumentCategory.STRUCTURAL_STABILITY_CERTIFICATE,
                                        description=f"Fictional reuse fixture ({ds.docs[fixture_key].recipe})",
                                        seed_key=doc_key)
        result.created.append(doc_key)
    session.commit()
    return result


class FixtureResetRefused(Exception):
    pass


def reset(session: Session, settings: Settings, *, confirm: bool) -> int:
    """Delete only the reuse fixture rows (seed_key ``reuse-…``) and their dependants. Returns files removed."""
    if not confirm:
        raise FixtureResetRefused("Refusing to reset reuse fixtures: pass --confirm-reset.")
    if settings.environment not in ("development", "test"):
        raise FixtureResetRefused(f"Refusing to reset reuse fixtures in the '{settings.environment}' environment.")
    app_ids = list(session.execute(select(Application.id).where(Application.seed_key.like(f"{PREFIX}%"))).scalars())
    inst_ids = list(session.execute(select(Institution.id).where(Institution.seed_key.like(f"{PREFIX}%"))).scalars())
    docs = list(session.execute(select(Document).where(Document.application_id.in_(app_ids))).scalars())
    doc_ids = [d.id for d in docs]
    keys = [d.storage_key for d in docs if d.storage_key]
    pair_filter = or_(CasePair.application_a_id.in_(app_ids), CasePair.application_b_id.in_(app_ids))
    session.execute(delete(CasePair).where(pair_filter))  # evidence and actions cascade
    session.execute(delete(ReuseScanRun).where(ReuseScanRun.application_id.in_(app_ids)))
    session.execute(delete(DocumentFingerprint).where(DocumentFingerprint.document_id.in_(doc_ids)))
    alert_ids = list(session.execute(select(Alert.id).where(Alert.application_id.in_(app_ids))).scalars())
    session.execute(delete(AlertRead).where(AlertRead.alert_id.in_(alert_ids)))
    session.execute(delete(Alert).where(Alert.id.in_(alert_ids)))
    req_ids = list(session.execute(select(EvidenceRequest.id).where(EvidenceRequest.application_id.in_(app_ids))).scalars())
    session.execute(delete(EvidenceRequestDocument).where(EvidenceRequestDocument.evidence_request_id.in_(req_ids)))
    session.execute(delete(EvidenceRequest).where(EvidenceRequest.id.in_(req_ids)))
    session.execute(delete(FindingReviewAction).where(FindingReviewAction.application_id.in_(app_ids)))
    run_ids = list(session.execute(select(ScrutinyRun.id).where(ScrutinyRun.application_id.in_(app_ids))).scalars())
    session.execute(delete(VerificationAttempt).where(VerificationAttempt.application_id.in_(app_ids)))
    for model in (Finding, RuleEvaluation):
        session.execute(delete(model).where(model.run_id.in_(run_ids)))
    session.execute(delete(ScrutinyRun).where(ScrutinyRun.id.in_(run_ids)))
    proc_ids = list(session.execute(select(DocumentProcessing.id).where(DocumentProcessing.document_id.in_(doc_ids))).scalars())
    session.execute(delete(ExtractedField).where(ExtractedField.processing_id.in_(proc_ids)))
    session.execute(delete(DocumentPage).where(DocumentPage.processing_id.in_(proc_ids)))
    session.execute(delete(DocumentProcessing).where(DocumentProcessing.id.in_(proc_ids)))
    session.execute(update(Document).where(Document.duplicate_of_id.in_(doc_ids)).values(duplicate_of_id=None))
    session.execute(delete(Document).where(Document.id.in_(doc_ids)))
    session.execute(delete(ApplicationProgramme).where(ApplicationProgramme.application_id.in_(app_ids)))
    session.execute(delete(Application).where(Application.id.in_(app_ids)))
    session.execute(delete(Institution).where(Institution.id.in_(inst_ids)))
    audit.record(session, "reuse_fixtures.reset", "database", None,
                 details={"applications": len(app_ids), "documents": len(doc_ids)})
    session.commit()
    storage = DocumentStorage(settings.document_storage_path)
    removed = 0
    for key in keys:
        path = storage.open_path(key)
        if path is not None:
            DocumentStorage.discard(path)
            removed += 1
    return removed
