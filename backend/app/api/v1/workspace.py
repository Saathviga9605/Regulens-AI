"""Reviewer workspace: queue, review actions, evidence requests, audit, alerts, reports and copilot."""

import math
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_current_actor, get_db, get_pagination, require_admin
from app.core.context import Actor
from app.core.errors import AppError, NotFoundError
from app.models import Application, Document, ScrutinyRun
from app.models.enums import ApplicationStatus, AuditOutcome, Severity
from app.schemas.common import Page
from app.schemas.workspace import (
    AlertPage,
    AlertRead,
    AuditEventRead,
    CopilotAnswer,
    CopilotQuestion,
    EvidenceClose,
    EvidenceLink,
    EvidenceRequestCreate,
    EvidenceRequestRead,
    LinkedDocumentRead,
    MarkRead,
    QueueItem,
    QueuePage,
    ReviewActionRead,
    ReviewActionRequest,
)
from app.services import alerts, audit, copilot, queue, report, review
from app.services.applications import get_application
from app.services.scrutiny import get_run

router = APIRouter(tags=["workspace"])


# --- Queue -------------------------------------------------------------------------------------------

@router.get("/review-queue", response_model=QueuePage)
def review_queue(
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(None, max_length=100),
    status: ApplicationStatus | None = None,
    scrutiny_status: str | None = Query(None, pattern=r"^(none|completed|completed_with_warnings|failed|running)$"),
    severity: Severity | None = None,
    unresolved_only: bool = False,
    review_state: str | None = Query(None, pattern=r"^(no_scrutiny|not_started|in_progress|complete)$"),
    sort: str = Query("priority", pattern=r"^(priority|application_code|updated)$"),
    db: Session = Depends(get_db),
) -> QueuePage:
    rows, counts = queue.query(db, q=q, status=status, scrutiny_status=scrutiny_status, severity=severity,
                               unresolved_only=unresolved_only, review_state=review_state, sort=sort)
    start = (pagination.page - 1) * pagination.page_size
    items = [QueueItem(
        application_code=r.application.application_code, institution_name=r.application.institution.name,
        institution_code=r.application.institution.institution_code,
        application_type=r.application.application_type.value, academic_year=r.application.academic_year,
        status=r.application.status, latest_run_number=r.latest_run.run_number if r.latest_run else None,
        latest_run_status=r.latest_run.status.value if r.latest_run else None,
        latest_run_finished_at=r.latest_run.finished_at if r.latest_run else None,
        unresolved_by_severity=r.unresolved_by_severity, unresolved_total=r.unresolved_total,
        findings_total=r.findings_total, open_evidence_requests=r.open_requests,
        overdue_evidence_requests=r.overdue_requests, review_state=r.review_state,
    ) for r in rows[start:start + pagination.page_size]]
    return QueuePage(items=items, total=len(rows), page=pagination.page, page_size=pagination.page_size,
                     total_pages=math.ceil(len(rows) / pagination.page_size) if rows else 0, counts=counts)


# --- Review actions ----------------------------------------------------------------------------------

@router.post("/applications/{application_code}/findings/{finding_id}/actions", response_model=ReviewActionRead,
             status_code=201)
def review_action(application_code: str, finding_id: str, body: ReviewActionRequest,
                  actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)) -> ReviewActionRead:
    application = get_application(db, application_code)
    entry = review.apply_action(db, application, finding_id, actor, action=body.action,
                                expected_version=body.expected_version, note=body.note,
                                evidence_refs=[r.model_dump() for r in body.evidence_refs],
                                requested_evidence=body.requested_evidence, due_date=body.due_date)
    return ReviewActionRead.model_validate(entry)


@router.get("/applications/{application_code}/findings/{finding_id}/actions", response_model=list[ReviewActionRead])
def finding_actions(application_code: str, finding_id: str, db: Session = Depends(get_db)) -> list[ReviewActionRead]:
    application = get_application(db, application_code)
    finding = review.scoped_finding(db, application, finding_id)
    return [ReviewActionRead.model_validate(a) for a in review.history(db, finding)]


@router.get("/applications/{application_code}/review-actions", response_model=list[ReviewActionRead])
def application_actions(application_code: str, db: Session = Depends(get_db)) -> list[ReviewActionRead]:
    return [ReviewActionRead.model_validate(a) for a in review.application_history(db, get_application(db, application_code))]


# --- Evidence requests -------------------------------------------------------------------------------

def _request_read(code: str, r) -> EvidenceRequestRead:
    return EvidenceRequestRead(
        id=r.id, application_code=code, finding_id=r.finding_id, finding_title=r.finding_title,
        requested_evidence=r.requested_evidence, reason=r.reason, due_date=r.due_date, status=r.status,
        is_overdue=review.is_overdue(r), version=r.version, created_by=r.created_by, created_at=r.created_at,
        closed_by=r.closed_by, closed_at=r.closed_at, closing_note=r.closing_note,
        documents=[LinkedDocumentRead.model_validate(d) for d in r.documents])


@router.get("/applications/{application_code}/evidence-requests", response_model=list[EvidenceRequestRead])
def list_evidence_requests(application_code: str,
                           status: str | None = Query(None, pattern=r"^(open|fulfilled|cancelled|overdue)$"),
                           db: Session = Depends(get_db)) -> list[EvidenceRequestRead]:
    application = get_application(db, application_code)
    return [_request_read(application_code, r) for r in review.list_requests(db, application, status)]


@router.post("/applications/{application_code}/evidence-requests", response_model=EvidenceRequestRead, status_code=201)
def create_evidence_request(application_code: str, body: EvidenceRequestCreate,
                            actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)) -> EvidenceRequestRead:
    application = get_application(db, application_code)
    finding = review.scoped_finding(db, application, body.finding_id) if body.finding_id else None
    r = review.create_evidence_request(db, application, actor, requested_evidence=body.requested_evidence,
                                       reason=body.reason, due_date=body.due_date, finding=finding)
    return _request_read(application_code, r)


@router.post("/applications/{application_code}/evidence-requests/{request_id}/documents",
             response_model=EvidenceRequestRead, status_code=201)
def link_evidence(application_code: str, request_id: str, body: EvidenceLink, actor: Actor = Depends(get_current_actor),
                  db: Session = Depends(get_db)) -> EvidenceRequestRead:
    application = get_application(db, application_code)
    r = review.scoped_request(db, application, request_id)
    document = db.get(Document, body.document_id)
    if document is None or document.application_id != application.id:
        raise NotFoundError("Document was not found.")
    review.link_document(db, application, r, document, actor)
    return _request_read(application_code, r)


@router.post("/applications/{application_code}/evidence-requests/{request_id}/fulfil", response_model=EvidenceRequestRead)
def fulfil_evidence(application_code: str, request_id: str, body: EvidenceClose, actor: Actor = Depends(get_current_actor),
                    db: Session = Depends(get_db)) -> EvidenceRequestRead:
    application = get_application(db, application_code)
    r = review.fulfil(db, application, review.scoped_request(db, application, request_id), actor, note=body.note,
                      expected_version=body.expected_version)
    return _request_read(application_code, r)


@router.post("/applications/{application_code}/evidence-requests/{request_id}/cancel", response_model=EvidenceRequestRead)
def cancel_evidence(application_code: str, request_id: str, body: EvidenceClose, actor: Actor = Depends(get_current_actor),
                    db: Session = Depends(get_db)) -> EvidenceRequestRead:
    application = get_application(db, application_code)
    r = review.cancel(db, application, review.scoped_request(db, application, request_id), actor,
                      reason=body.note or "", expected_version=body.expected_version)
    return _request_read(application_code, r)


# --- Audit -------------------------------------------------------------------------------------------

@router.get("/audit-events", response_model=Page[AuditEventRead], dependencies=[Depends(require_admin)])
def list_audit(pagination: Pagination = Depends(get_pagination), action: str | None = Query(None, max_length=60),
               actor: str | None = Query(None, max_length=60), outcome: AuditOutcome | None = None,
               resource_type: str | None = Query(None, max_length=40),
               application_code: str | None = Query(None, max_length=30), db: Session = Depends(get_db)):
    application_id = get_application(db, application_code).id if application_code else None
    rows, total = audit.list_events(db, page=pagination.page, page_size=pagination.page_size, action=action,
                                    actor=actor, outcome=outcome, resource_type=resource_type,
                                    application_id=application_id)
    return Page.build([AuditEventRead.model_validate(r) for r in rows], total, pagination.page, pagination.page_size)


@router.get("/applications/{application_code}/audit-events", response_model=Page[AuditEventRead])
def application_audit(application_code: str, pagination: Pagination = Depends(get_pagination),
                      action: str | None = Query(None, max_length=60), db: Session = Depends(get_db)):
    application = get_application(db, application_code)
    rows, total = audit.list_events(db, page=pagination.page, page_size=pagination.page_size,
                                    application_id=application.id, action=action)
    return Page.build([AuditEventRead.model_validate(r) for r in rows], total, pagination.page, pagination.page_size)


# --- Alerts ------------------------------------------------------------------------------------------

@router.get("/alerts", response_model=AlertPage)
def list_alerts(pagination: Pagination = Depends(get_pagination), unread_only: bool = False,
                application_code: str | None = Query(None, max_length=30),
                event_type: str | None = Query(None, max_length=40), actor: Actor = Depends(get_current_actor),
                db: Session = Depends(get_db)) -> AlertPage:
    alerts.refresh_due_alerts(db)
    application_id = get_application(db, application_code).id if application_code else None
    rows, total, read_ids, unread = alerts.list_alerts(db, actor.user_id, page=pagination.page,
                                                       page_size=pagination.page_size, unread_only=unread_only,
                                                       application_id=application_id, event_type=event_type)
    items = [AlertRead(id=a.id, application_code=code, event_type=a.event_type, severity=a.severity, title=a.title,
                       message=a.message, finding_id=a.finding_id, evidence_request_id=a.evidence_request_id,
                       document_id=a.document_id, created_at=a.created_at, read=a.id in read_ids) for a, code in rows]
    return AlertPage(items=items, total=total, page=pagination.page, page_size=pagination.page_size,
                     total_pages=math.ceil(total / pagination.page_size) if total else 0, unread_count=unread)


@router.post("/alerts/read", status_code=204, response_class=Response)
def mark_read(body: MarkRead, actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)) -> Response:
    from sqlalchemy import select

    from app.models import Alert

    known = set(db.execute(select(Alert.id).where(Alert.id.in_(body.alert_ids))).scalars())
    if len(known) != len(set(body.alert_ids)):
        raise NotFoundError("One or more alerts were not found.")
    alerts.mark_read(db, actor.user_id, list(known))
    return Response(status_code=204)


@router.post("/alerts/read-all", status_code=204, response_class=Response)
def mark_all_read(application_code: str | None = Query(None, max_length=30), actor: Actor = Depends(get_current_actor),
                  db: Session = Depends(get_db)) -> Response:
    from sqlalchemy import select

    from app.models import Alert

    stmt = select(Alert.id)
    if application_code:
        stmt = stmt.where(Alert.application_id == get_application(db, application_code).id)
    alerts.mark_read(db, actor.user_id, list(db.execute(stmt).scalars()))
    return Response(status_code=204)


# --- Report ------------------------------------------------------------------------------------------

@router.get("/applications/{application_code}/scrutiny-runs/{run_id}/report.pdf",
            responses={200: {"content": {"application/pdf": {}}}}, response_class=Response)
def download_report(application_code: str, run_id: str, db: Session = Depends(get_db)) -> Response:
    application = get_application(db, application_code)
    run: ScrutinyRun = get_run(db, run_id)
    if run.application_id != application.id:
        raise NotFoundError("Scrutiny run was not found.")
    if run.status.value in ("running", "failed"):
        raise AppError(409, "run_not_reportable", "Reports can only be generated for completed scrutiny runs.")
    data = report.build_report(db, application, run)
    name = report.safe_filename(application.application_code, run.run_number)
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store"})


# --- Copilot -----------------------------------------------------------------------------------------

@router.post("/applications/{application_code}/copilot", response_model=CopilotAnswer)
def ask_copilot(application_code: str, body: CopilotQuestion, db: Session = Depends(get_db)) -> CopilotAnswer:
    application: Application = get_application(db, application_code)
    if body.finding_id:
        review.scoped_finding(db, application, body.finding_id)
    result = copilot.answer_question(db, application, body.question, body.finding_id)
    return CopilotAnswer(intent=result.intent, lines=result.lines, sources=[asdict(s) for s in result.sources],
                         grounded=result.grounded, limitations=result.limitations, disclaimer=copilot.DISCLAIMER,
                         suggestions=copilot.SUGGESTIONS)
