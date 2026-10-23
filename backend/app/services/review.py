"""Human review of findings and additional-evidence requests.

Review actions append to ``finding_review_actions`` and update only the finding's human-review fields
(``review_status``, ``review_note``, ``reviewed_at``, ``review_version``); the system-generated outcome, explanation
and evidence are never changed. Each action, its audit event and any alert commit in one transaction.
Concurrency: clients send ``expected_version``; a mismatch returns 409 ``stale_review`` instead of overwriting.
Only findings of the application's latest scrutiny run can be acted on (older runs are history).

Review states are reviewer assessments. "confirmed" means a reviewer agrees the finding needs attention — not
proof of fraud or non-compliance. Nothing here approves or rejects an application.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import Actor
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.types import utcnow
from app.models import Application, Document, EvidenceRequest, EvidenceRequestDocument, Finding, FindingReviewAction
from app.models.enums import (
    DocumentStatus,
    EvidenceRequestStatus,
    ReviewActionType as A,
    ReviewStatus as S,
    Severity,
)
from app.services import alerts, audit
from app.services.scrutiny import latest_run

TRANSITIONS: dict[A, dict[S, S]] = {
    A.CONFIRM: {S.NOT_REVIEWED: S.CONFIRMED, S.ESCALATED: S.CONFIRMED, S.AWAITING_EVIDENCE: S.CONFIRMED},
    A.DISMISS: {s: S.DISMISSED for s in (S.NOT_REVIEWED, S.CONFIRMED, S.ESCALATED, S.AWAITING_EVIDENCE)},
    A.ESCALATE: {s: S.ESCALATED for s in (S.NOT_REVIEWED, S.CONFIRMED, S.AWAITING_EVIDENCE)},
    A.REQUEST_EVIDENCE: {s: S.AWAITING_EVIDENCE for s in (S.NOT_REVIEWED, S.CONFIRMED, S.ESCALATED,
                                                           S.AWAITING_EVIDENCE)},
    A.RESOLVE: {s: S.RESOLVED for s in (S.CONFIRMED, S.ESCALATED, S.AWAITING_EVIDENCE)},
    A.REOPEN: {S.DISMISSED: S.NOT_REVIEWED, S.RESOLVED: S.NOT_REVIEWED},
}
REASON_REQUIRED = {A.DISMISS, A.ESCALATE, A.RESOLVE, A.REOPEN, A.REQUEST_EVIDENCE, A.NOTE}
MIN_REASON = 10
UNRESOLVED = (S.NOT_REVIEWED, S.CONFIRMED, S.ESCALATED, S.AWAITING_EVIDENCE)


def allowed_actions(status: S) -> list[str]:
    return [a.value for a, table in TRANSITIONS.items() if status in table] + [A.NOTE.value]


def _reason(note: str | None, action: A) -> str | None:
    text = (note or "").strip()
    if action in REASON_REQUIRED and len(text) < MIN_REASON:
        raise AppError(422, "reason_required", f"A reason of at least {MIN_REASON} characters is required for "
                       f"'{action.value}'.", [{"loc": ["body", "note"], "msg": "Reason required."}])
    return text or None


def _validate_refs(session: Session, application_id: str, refs: list[dict]) -> list[dict]:
    clean = []
    for ref in refs:
        doc = session.get(Document, ref.get("document_id"))
        if doc is None or doc.application_id != application_id:
            raise AppError(422, "validation_error", "Evidence references must point to this application's documents.",
                           [{"loc": ["body", "evidence_refs"], "msg": "Unknown document."}])
        clean.append({"document_id": doc.id, "document_filename": doc.original_filename,
                      "page_number": ref.get("page_number")})
    return clean


def scoped_finding(session: Session, application: Application, finding_id: str) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None or finding.application_id != application.id:
        raise NotFoundError("Finding was not found.")
    return finding


def apply_action(session: Session, application: Application, finding_id: str, actor: Actor, *, action: A,
                 expected_version: int, note: str | None, evidence_refs: list[dict] | None = None,
                 requested_evidence: str | None = None, due_date: date | None = None) -> FindingReviewAction:
    finding = scoped_finding(session, application, finding_id)
    run = latest_run(session, application.id)
    if run is None or finding.run_id != run.id:
        raise ConflictError("finding_superseded", "This finding belongs to an earlier scrutiny run; act on the "
                            "corresponding finding in the latest run.")
    if finding.review_version != expected_version:
        raise ConflictError("stale_review", "This finding was updated by someone else. Reload and try again.",
                            [{"current_version": finding.review_version, "current_status": finding.review_status.value}])
    if action == A.CARRIED_FORWARD:
        raise AppError(422, "validation_error", "This action type is system-only.")
    previous = finding.review_status
    if action == A.NOTE:
        new = previous
    elif previous not in TRANSITIONS[action]:
        raise ConflictError("invalid_review_transition",
                            f"Cannot '{action.value}' a finding whose review state is '{previous.value}'.",
                            [{"allowed_actions": allowed_actions(previous)}])
    else:
        new = TRANSITIONS[action][previous]
    reason = _reason(note, action)
    refs = _validate_refs(session, application.id, evidence_refs or [])

    request = None
    if action == A.REQUEST_EVIDENCE:
        request = create_evidence_request(session, application, actor, requested_evidence=requested_evidence or "",
                                          reason=reason or "", due_date=due_date, finding=finding, commit=False)

    now = utcnow()
    entry = FindingReviewAction(finding_id=finding.id, application_id=application.id, action_type=action,
                                previous_status=previous, new_status=new, actor_user_id=actor.user_id,
                                actor_username=actor.username, note=reason, evidence_refs=refs,
                                evidence_request_id=request.id if request else None, created_at=now)
    session.add(entry)
    finding.review_status = new
    if reason:
        finding.review_note = reason[:1000]
    finding.reviewed_at = now
    finding.review_version += 1
    session.flush()
    audit.record(session, f"finding.{action.value}", "finding", finding.id, application_id=application.id,
                 details={"from": previous.value, "to": new.value, "finding_key": finding.finding_key,
                          "evidence_refs": len(refs), "evidence_request_id": request.id if request else None})
    if action == A.ESCALATE:
        alerts.raise_alert(session, dedup_key=f"escalated:{entry.id}", application_id=application.id,
                           event_type="finding_escalated", severity="high" if finding.severity == Severity.HIGH else "medium",
                           finding_id=finding.id, title="Finding escalated for further review",
                           message=f"{actor.username} escalated '{finding.title[:150]}' on {application.application_code}.")
    session.commit()
    return entry


def history(session: Session, finding: Finding) -> list[FindingReviewAction]:
    return list(session.execute(select(FindingReviewAction).where(FindingReviewAction.finding_id == finding.id)
                                .order_by(FindingReviewAction.created_at, FindingReviewAction.id)).scalars())


def application_history(session: Session, application: Application, limit: int = 100) -> list[FindingReviewAction]:
    return list(session.execute(select(FindingReviewAction).where(FindingReviewAction.application_id == application.id)
                                .order_by(FindingReviewAction.created_at.desc(), FindingReviewAction.id.desc())
                                .limit(limit)).scalars())


def carry_forward(session: Session, run_id: str, previous_run_id: str | None, application_id: str) -> int:
    """Copy human review state to identical findings (same finding_key) of a new run, with a history entry."""
    if previous_run_id is None:
        return 0
    old = {f.finding_key: f for f in session.execute(select(Finding).where(Finding.run_id == previous_run_id)).scalars()}
    count = 0
    for finding in session.execute(select(Finding).where(Finding.run_id == run_id)).scalars():
        prior = old.get(finding.finding_key)
        if prior is None or prior.review_status == S.NOT_REVIEWED:
            continue
        finding.review_status, finding.review_note, finding.reviewed_at = (prior.review_status, prior.review_note,
                                                                           prior.reviewed_at)
        session.add(FindingReviewAction(finding_id=finding.id, application_id=application_id,
                                        action_type=A.CARRIED_FORWARD, previous_status=S.NOT_REVIEWED,
                                        new_status=prior.review_status, actor_user_id=None, actor_username="system",
                                        note=f"Review state carried forward from finding {prior.id} of the previous run."))
        count += 1
    return count


# --- Evidence requests --------------------------------------------------------------------------------

def _request_text(value: str, name: str, minimum: int) -> str:
    text = (value or "").strip()
    if len(text) < minimum:
        raise AppError(422, "validation_error", f"'{name}' must be at least {minimum} characters.",
                       [{"loc": ["body", name], "msg": "Too short."}])
    return text[:2000]


def create_evidence_request(session: Session, application: Application, actor: Actor, *, requested_evidence: str,
                            reason: str, due_date: date | None = None, finding: Finding | None = None,
                            commit: bool = True) -> EvidenceRequest:
    if due_date and due_date < date.today():
        raise AppError(422, "validation_error", "The due date cannot be in the past.",
                       [{"loc": ["body", "due_date"], "msg": "Past date."}])
    request = EvidenceRequest(application_id=application.id, finding_id=finding.id if finding else None,
                              finding_title=finding.title if finding else None,
                              requested_evidence=_request_text(requested_evidence, "requested_evidence", 5),
                              reason=_request_text(reason, "reason", MIN_REASON),
                              due_date=due_date.isoformat() if due_date else None, created_by=actor.username)
    session.add(request)
    session.flush()
    audit.record(session, "evidence_request.created", "evidence_request", request.id, application_id=application.id,
                 details={"finding_id": request.finding_id, "due_date": request.due_date})
    alerts.raise_alert(session, dedup_key=f"evidence_requested:{request.id}", application_id=application.id,
                       event_type="evidence_requested", severity="medium", evidence_request_id=request.id,
                       finding_id=request.finding_id, title="Additional evidence requested",
                       message=f"{actor.username} requested: {request.requested_evidence[:200]}"
                       + (f" (due {request.due_date})" if request.due_date else ""))
    if commit:
        session.commit()
    return request


def scoped_request(session: Session, application: Application, request_id: str) -> EvidenceRequest:
    request = session.get(EvidenceRequest, request_id)
    if request is None or request.application_id != application.id:
        raise NotFoundError("Evidence request was not found.")
    return request


def _require_open(request: EvidenceRequest, expected_version: int | None) -> None:
    if request.status != EvidenceRequestStatus.OPEN:
        raise ConflictError("evidence_request_closed", f"This evidence request is already {request.status.value}.")
    if expected_version is not None and expected_version != request.version:
        raise ConflictError("stale_evidence_request", "This request was updated by someone else. Reload and retry.")


def link_document(session: Session, application: Application, request: EvidenceRequest, document: Document,
                  actor: Actor, *, commit: bool = True) -> EvidenceRequestDocument:
    _require_open(request, None)
    if document.application_id != application.id or document.status == DocumentStatus.INTAKE_FAILED:
        raise AppError(422, "validation_error", "Only successfully uploaded documents of this application can be linked.")
    if any(link.document_id == document.id for link in request.documents):
        raise ConflictError("already_linked", "This document is already linked to the request.")
    link = EvidenceRequestDocument(evidence_request_id=request.id, document_id=document.id,
                                   document_filename=document.original_filename, linked_by=actor.username)
    request.documents.append(link)
    request.version += 1
    session.flush()
    audit.record(session, "evidence_request.document_linked", "evidence_request", request.id,
                 application_id=application.id, details={"document_id": document.id})
    alerts.raise_alert(session, dedup_key=f"evidence_uploaded:{request.id}:{document.id}",
                       application_id=application.id, event_type="evidence_uploaded", evidence_request_id=request.id,
                       document_id=document.id, title="New evidence linked to a request",
                       message=f"'{document.original_filename}' was linked to the request "
                               f"'{request.requested_evidence[:120]}'.")
    if commit:
        session.commit()
    return link


def fulfil(session: Session, application: Application, request: EvidenceRequest, actor: Actor, *, note: str | None,
           expected_version: int) -> EvidenceRequest:
    _require_open(request, expected_version)
    if not request.documents:
        raise ConflictError("no_linked_evidence", "Link at least one uploaded document before marking fulfilled.")
    request.status, request.closed_by, request.closed_at = EvidenceRequestStatus.FULFILLED, actor.username, utcnow()
    request.closing_note = (note or "").strip()[:2000] or None
    request.version += 1
    audit.record(session, "evidence_request.fulfilled", "evidence_request", request.id, application_id=application.id,
                 details={"documents": len(request.documents)})
    session.commit()
    return request


def cancel(session: Session, application: Application, request: EvidenceRequest, actor: Actor, *, reason: str,
           expected_version: int) -> EvidenceRequest:
    _require_open(request, expected_version)
    request.status, request.closed_by, request.closed_at = EvidenceRequestStatus.CANCELLED, actor.username, utcnow()
    request.closing_note = _request_text(reason, "reason", MIN_REASON)
    request.version += 1
    audit.record(session, "evidence_request.cancelled", "evidence_request", request.id, application_id=application.id)
    session.commit()
    return request


def list_requests(session: Session, application: Application, status: str | None = None) -> list[EvidenceRequest]:
    stmt = select(EvidenceRequest).where(EvidenceRequest.application_id == application.id)
    today = date.today().isoformat()
    if status == "overdue":
        stmt = stmt.where(EvidenceRequest.status == EvidenceRequestStatus.OPEN, EvidenceRequest.due_date < today)
    elif status:
        stmt = stmt.where(EvidenceRequest.status == EvidenceRequestStatus(status))
    return list(session.execute(stmt.order_by(EvidenceRequest.created_at.desc(), EvidenceRequest.id)).scalars())


def is_overdue(request: EvidenceRequest) -> bool:
    return (request.status == EvidenceRequestStatus.OPEN and request.due_date is not None
            and request.due_date < date.today().isoformat())
