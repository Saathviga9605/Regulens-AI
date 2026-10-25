"""Document processing, preliminary scrutiny, findings and simulated issuer verification endpoints.

Processing and scrutiny run synchronously within the request (bounded by page/OCR limits). Runs and findings
are addressed under their application so records cannot be read through another application's URL.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_app_settings, get_db, get_pagination, get_storage, require_admin
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.types import utcnow
from app.models import Application, ScrutinyRule, VerificationAttempt
from app.models.enums import FindingKind, ReviewStatus, RuleOutcome, Severity
from app.schemas.common import Page, StrictInputModel
from app.schemas.scrutiny import (
    ClassificationRead,
    EvaluationRead,
    ExtractedFieldRead,
    FindingDetail,
    FindingRead,
    PageRead,
    PageSummary,
    ProcessingRead,
    RuleCreate,
    RuleRead,
    RuleUpdate,
    RunRead,
    RunSummaryRead,
    VerificationAttemptRead,
)
from app.services import source_status
from app.services import documents as document_service
from app.services import audit, issuer_verification, processing as processing_service, review, rule_catalog, scrutiny
from app.services.applications import get_application
from app.services.storage import DocumentStorage

router = APIRouter(tags=["scrutiny"])


def get_ocr(request: Request):
    return request.app.state.ocr_engine


# --- Processing -----------------------------------------------------------------------------------

def _processing_read(session: Session, document, processing, reused: bool | None = None) -> ProcessingRead:
    predicted = processing.predicted_category
    return ProcessingRead(
        document_id=document.id, application_code=document.application.application_code, status=processing.status,
        failure_code=processing.failure_code, failure_reason=processing.failure_reason,
        pipeline_version=processing.pipeline_version, is_current=processing_service.is_current(processing, document),
        reused_from_cache=processing.reused_from_cache if reused is None else (reused or processing.reused_from_cache),
        ocr_available=processing.ocr_available, page_count=processing.page_count,
        pages_processed=processing.pages_processed, warnings=processing.warnings,
        classification=ClassificationRead(
            predicted_category=predicted, selected_category=document.category,
            confidence=processing.classification_confidence, score=processing.classification_score,
            signals=processing.classification_signals, alternatives=processing.classification_alternatives,
            agrees_with_selected=None if predicted is None else predicted == document.category),
        pages=[PageSummary(page_number=p.page_number, method=p.method, status=p.status, char_count=p.char_count,
                           warnings=p.warnings, ocr_engine=p.ocr_engine, ocr_confidence=p.ocr_confidence,
                           rotation_degrees=p.rotation_degrees) for p in processing.pages],
        fields=[ExtractedFieldRead.model_validate(f) for f in processing.fields],
        started_at=processing.started_at, finished_at=processing.finished_at,
    )


@router.post("/documents/{document_id}/processing", response_model=ProcessingRead)
def process_document(document_id: str, force: bool = Query(False, description="Reprocess even if cached"),
                     db: Session = Depends(get_db), storage: DocumentStorage = Depends(get_storage),
                     settings: Settings = Depends(get_app_settings), ocr=Depends(get_ocr)) -> ProcessingRead:
    document = document_service.get_document(db, document_id)
    processing, reused = processing_service.process_document(db, storage, settings, ocr, document, force=force)
    return _processing_read(db, document, processing, reused)


def _require_processing(db: Session, document_id: str):
    document = document_service.get_document(db, document_id)
    processing = processing_service.get_processing(db, document_id)
    if processing is None:
        raise AppError(404, "not_processed", "This document has not been processed yet.")
    return document, processing


@router.get("/documents/{document_id}/processing", response_model=ProcessingRead)
def get_processing(document_id: str, db: Session = Depends(get_db)) -> ProcessingRead:
    document, processing = _require_processing(db, document_id)
    return _processing_read(db, document, processing)


@router.get("/documents/{document_id}/pages", response_model=Page[PageRead])
def get_pages(document_id: str, pagination: Pagination = Depends(get_pagination),
              db: Session = Depends(get_db)) -> Page[PageRead]:
    _, processing = _require_processing(db, document_id)
    start = (pagination.page - 1) * pagination.page_size
    pages = processing.pages[start:start + pagination.page_size]
    return Page.build([PageRead.model_validate(p) for p in pages], len(processing.pages), pagination.page,
                      pagination.page_size)


# --- Simulated issuer verification ----------------------------------------------------------------

def _attempt_read(a: VerificationAttempt) -> VerificationAttemptRead:
    return VerificationAttemptRead(
        id=a.id, document_id=a.document_id, document_filename=a.document_filename, adapter=a.adapter,
        method=a.method, simulated=a.simulated,
        simulation_label=issuer_verification.SIMULATION_LABEL if a.simulated else None, outcome=a.outcome,
        explanation=a.explanation, fields_compared=a.fields_compared, reference_code=a.reference_code,
        source_status=a.source_status.value, source_status_label=source_status.LABELS[a.source_status],
        source_type=a.source_type.value, created_at=a.created_at)


@router.post("/documents/{document_id}/issuer-verifications", response_model=VerificationAttemptRead,
             status_code=201)
def run_issuer_verification(document_id: str, db: Session = Depends(get_db)) -> VerificationAttemptRead:
    document = document_service.get_document(db, document_id)
    return _attempt_read(issuer_verification.verify_document(db, document, date.today()))


@router.get("/documents/{document_id}/issuer-verifications", response_model=list[VerificationAttemptRead])
def list_document_verifications(document_id: str, db: Session = Depends(get_db)) -> list[VerificationAttemptRead]:
    document_service.get_document(db, document_id)
    rows = db.execute(select(VerificationAttempt).where(VerificationAttempt.document_id == document_id)
                      .order_by(VerificationAttempt.created_at.desc(), VerificationAttempt.id).limit(50)).scalars()
    return [_attempt_read(a) for a in rows]


@router.get("/applications/{application_code}/issuer-verifications", response_model=Page[VerificationAttemptRead])
def list_application_verifications(application_code: str, pagination: Pagination = Depends(get_pagination),
                                   db: Session = Depends(get_db)) -> Page[VerificationAttemptRead]:
    application = get_application(db, application_code)
    base = select(VerificationAttempt).where(VerificationAttempt.application_id == application.id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(VerificationAttempt.created_at.desc(), VerificationAttempt.id)
                      .limit(pagination.page_size).offset((pagination.page - 1) * pagination.page_size)).scalars()
    return Page.build([_attempt_read(a) for a in rows], total, pagination.page, pagination.page_size)


# --- Rules ------------------------------------------------------------------------------------------

def _validated_params(rule_type, parameters: dict) -> dict:
    try:
        return rule_catalog.validate_parameters(rule_type, parameters)
    except ValidationError as exc:
        details = [{"loc": ["body", "parameters", *[str(x) for x in e["loc"]]], "msg": e["msg"]} for e in exc.errors()]
        raise AppError(422, "validation_error", "Rule parameters are invalid for this rule type.", details) from None


@router.get("/scrutiny-rules", response_model=list[RuleRead])
def list_rules(db: Session = Depends(get_db)) -> list[RuleRead]:
    return [RuleRead.model_validate(r) for r in db.execute(select(ScrutinyRule).order_by(ScrutinyRule.rule_id)).scalars()]


def _get_rule(db: Session, rule_id: str) -> ScrutinyRule:
    rule = db.get(ScrutinyRule, rule_id)
    if rule is None:
        raise NotFoundError(f"Rule '{rule_id}' was not found.")
    return rule


@router.get("/scrutiny-rules/{rule_id}", response_model=RuleRead)
def get_rule(rule_id: str, db: Session = Depends(get_db)) -> RuleRead:
    return RuleRead.model_validate(_get_rule(db, rule_id))


@router.post("/scrutiny-rules", response_model=RuleRead, status_code=201, dependencies=[Depends(require_admin)])
def create_rule(body: RuleCreate, db: Session = Depends(get_db)) -> RuleRead:
    if db.get(ScrutinyRule, body.rule_id) is not None:
        raise ConflictError("rule_exists", f"Rule '{body.rule_id}' already exists.")
    data = body.model_dump()
    data["parameters"] = _validated_params(body.rule_type, body.parameters)
    rule = ScrutinyRule(**data, version=1)
    db.add(rule)
    audit.record(db, "rule.created", "scrutiny_rule", rule.rule_id,
                 details={"rule_type": rule.rule_type.value, "is_demo_only": rule.is_demo_only})
    db.commit()
    return RuleRead.model_validate(rule)


@router.patch("/scrutiny-rules/{rule_id}", response_model=RuleRead, dependencies=[Depends(require_admin)])
def update_rule(rule_id: str, body: RuleUpdate, db: Session = Depends(get_db)) -> RuleRead:
    rule = _get_rule(db, rule_id)
    changes = body.model_dump(exclude_unset=True)
    if rule.registry_managed:
        if set(changes) != {"enabled"}:
            raise ConflictError(
                "registry_rule_immutable",
                "Registry-managed rule content is immutable; only its enabled state can be changed.",
            )
        if rule.enabled != changes["enabled"]:
            previous_enabled = rule.enabled
            rule.enabled = changes["enabled"]
            rule.updated_at = utcnow()
            audit.record(
                db, "registry_rule.enabled_changed", "scrutiny_rule", rule.rule_id,
                details={"enabled_from": previous_enabled, "enabled_to": rule.enabled,
                         "version": rule.version},
            )
            db.commit()
        return RuleRead.model_validate(rule)
    if "parameters" in changes:
        changes["parameters"] = _validated_params(rule.rule_type, changes["parameters"])
    changed = {k: v for k, v in changes.items() if getattr(rule, k) != v}
    if changed:
        for key, value in changed.items():
            setattr(rule, key, value)
        rule.version += 1  # runs snapshot rule versions, so history stays reproducible
        rule.updated_at = utcnow()
        audit.record(db, "rule.updated", "scrutiny_rule", rule.rule_id,
                     details={"changed": sorted(changed), "version": rule.version, "enabled": rule.enabled})
        db.commit()
    return RuleRead.model_validate(rule)


# --- Runs and findings ------------------------------------------------------------------------------

class RunRequest(StrictInputModel):
    scrutiny_date: date | None = None
    ruleset_profile: Literal["production", "aph_eoa_demo"] = "aph_eoa_demo"


def _run_summary(run, code: str) -> dict:
    profile = next((item for item in run.rule_snapshot if item.get("ruleset_profile")), None)
    return dict(id=run.id, application_code=code, run_number=run.run_number, status=run.status,
                scrutiny_date=run.scrutiny_date, scrutiny_date_source=run.scrutiny_date_source,
                rule_set_version=run.rule_set_version, summary=run.summary,
                ruleset_profile=profile["ruleset_profile"] if profile else "production",
                ruleset_profile_version=profile["ruleset_version"] if profile else "database",
                warnings=run.warnings, failure_reason=run.failure_reason, started_at=run.started_at,
                finished_at=run.finished_at)


def _scoped_run(db: Session, application_code: str, run_id: str):
    application = get_application(db, application_code)
    run = scrutiny.get_run(db, run_id)
    scrutiny.ensure_application_scope(run, application.id)
    return application, run


@router.post("/applications/{application_code}/scrutiny-runs", response_model=RunRead, status_code=201)
def start_run(application_code: str, body: RunRequest | None = Body(None), db: Session = Depends(get_db),
              storage: DocumentStorage = Depends(get_storage), settings: Settings = Depends(get_app_settings),
              ocr=Depends(get_ocr)) -> RunRead:
    scrutiny_date = body.scrutiny_date if body else None
    ruleset_profile = body.ruleset_profile if body else "aph_eoa_demo"
    if scrutiny_date and not date(2000, 1, 1) <= scrutiny_date <= date(2100, 12, 31):
        raise AppError(422, "validation_error", "scrutiny_date is out of range.")
    run = scrutiny.start_run(db, storage, settings, ocr, application_code, scrutiny_date, ruleset_profile)
    return RunRead(**_run_summary(run, application_code), rule_snapshot=run.rule_snapshot,
                   documents_considered=run.documents_considered,
                   evaluations=[EvaluationRead.model_validate(e) for e in run.evaluations])


@router.get("/applications/{application_code}/scrutiny-runs", response_model=Page[RunSummaryRead])
def list_runs(application_code: str, pagination: Pagination = Depends(get_pagination),
              db: Session = Depends(get_db)) -> Page[RunSummaryRead]:
    rows, total = scrutiny.list_runs(db, application_code, pagination.page, pagination.page_size)
    return Page.build([RunSummaryRead(**_run_summary(r, application_code)) for r in rows], total, pagination.page,
                      pagination.page_size)


@router.get("/applications/{application_code}/scrutiny-runs/{run_id}", response_model=RunRead)
def get_run(application_code: str, run_id: str, db: Session = Depends(get_db)) -> RunRead:
    _, run = _scoped_run(db, application_code, run_id)
    return RunRead(**_run_summary(run, application_code), rule_snapshot=run.rule_snapshot,
                   documents_considered=run.documents_considered,
                   evaluations=[EvaluationRead.model_validate(e) for e in run.evaluations])


def _findings_page(db, run, pagination, severity, kind, outcome, review_status) -> Page[FindingRead]:
    rows, total = scrutiny.list_findings(db, run, page=pagination.page, page_size=pagination.page_size,
                                         severity=severity, kind=kind, outcome=outcome, review_status=review_status)
    items = [FindingRead.model_validate(f).model_copy(update={"allowed_actions": review.allowed_actions(f.review_status)})
             for f in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/applications/{application_code}/scrutiny-runs/{run_id}/findings", response_model=Page[FindingRead])
def list_run_findings(application_code: str, run_id: str, pagination: Pagination = Depends(get_pagination),
                      severity: Severity | None = None, kind: FindingKind | None = None,
                      outcome: RuleOutcome | None = None, review_status: ReviewStatus | None = None,
                      db: Session = Depends(get_db)) -> Page[FindingRead]:
    _, run = _scoped_run(db, application_code, run_id)
    return _findings_page(db, run, pagination, severity, kind, outcome, review_status)


@router.get("/applications/{application_code}/findings", response_model=Page[FindingRead])
def list_latest_findings(application_code: str, pagination: Pagination = Depends(get_pagination),
                         severity: Severity | None = None, kind: FindingKind | None = None,
                         outcome: RuleOutcome | None = None, review_status: ReviewStatus | None = None,
                         db: Session = Depends(get_db)) -> Page[FindingRead]:
    """Findings of the most recent run (empty page if no run exists)."""
    application = get_application(db, application_code)
    run = scrutiny.latest_run(db, application.id)
    if run is None:
        return Page.build([], 0, pagination.page, pagination.page_size)
    return _findings_page(db, run, pagination, severity, kind, outcome, review_status)


def _finding_detail(db: Session, application: Application, finding) -> FindingDetail:
    run = scrutiny.get_run(db, finding.run_id)
    base = FindingRead.model_validate(finding).model_dump()
    base["allowed_actions"] = review.allowed_actions(finding.review_status)
    return FindingDetail(**base,
                         application_code=application.application_code, run_number=run.run_number,
                         rule=scrutiny.evaluation_rule(run.rule_snapshot, finding.rule_id))


@router.get("/applications/{application_code}/findings/{finding_id}", response_model=FindingDetail)
def get_finding(application_code: str, finding_id: str, db: Session = Depends(get_db)) -> FindingDetail:
    application = get_application(db, application_code)
    finding = scrutiny.get_finding(db, finding_id)
    scrutiny.ensure_application_scope(finding, application.id)
    return _finding_detail(db, application, finding)
