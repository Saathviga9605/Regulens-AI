"""In-app alerts generated from backend events.

Every alert has a deterministic ``dedup_key``; ``raise_alert`` is a no-op when the key exists, so reruns and list
refreshes never duplicate an alert. All alerts are visible to all staff (reviewers and administrators) because the
prototype has no per-application assignment; read state is per user. No email/SMS is sent.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, AlertRead, Application, EvidenceRequest
from app.models.enums import EvidenceRequestStatus

DUE_SOON_DAYS = 2


def raise_alert(session: Session, *, dedup_key: str, application_id: str, event_type: str, title: str,
                message: str, severity: str = "info", finding_id: str | None = None,
                evidence_request_id: str | None = None, document_id: str | None = None) -> bool:
    pending = any(isinstance(o, Alert) and o.dedup_key == dedup_key for o in session.new)
    if pending or session.execute(select(Alert.id).where(Alert.dedup_key == dedup_key)).first():
        return False
    session.add(Alert(dedup_key=dedup_key[:200], application_id=application_id, event_type=event_type,
                      severity=severity, title=title[:200], message=message[:1000], finding_id=finding_id,
                      evidence_request_id=evidence_request_id, document_id=document_id))
    return True


def refresh_due_alerts(session: Session, today: date | None = None) -> None:
    """Time-based alerts for open evidence requests (idempotent)."""
    today = today or date.today()
    soon = (today + timedelta(days=DUE_SOON_DAYS)).isoformat()
    rows = session.execute(select(EvidenceRequest).where(EvidenceRequest.status == EvidenceRequestStatus.OPEN,
                                                         EvidenceRequest.due_date.is_not(None),
                                                         EvidenceRequest.due_date <= soon)).scalars().all()
    changed = False
    for req in rows:
        overdue = req.due_date < today.isoformat()
        kind = "evidence_overdue" if overdue else "evidence_due_soon"
        changed |= raise_alert(
            session, dedup_key=f"{kind}:{req.id}", application_id=req.application_id, event_type=kind,
            severity="medium" if overdue else "low", evidence_request_id=req.id,
            title="Evidence request overdue" if overdue else "Evidence request due soon",
            message=f"Requested evidence ('{req.requested_evidence[:120]}') was due on {req.due_date}."
            if overdue else f"Requested evidence ('{req.requested_evidence[:120]}') is due on {req.due_date}.")
    if changed:
        session.commit()


def list_alerts(session: Session, user_id: str, *, page: int, page_size: int, unread_only: bool = False,
                application_id: str | None = None, event_type: str | None = None):
    read = select(AlertRead.alert_id).where(AlertRead.user_id == user_id)
    stmt = select(Alert, Application.application_code).join(Application, Application.id == Alert.application_id)
    if unread_only:
        stmt = stmt.where(Alert.id.not_in(read))
    if application_id:
        stmt = stmt.where(Alert.application_id == application_id)
    if event_type:
        stmt = stmt.where(Alert.event_type == event_type)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(page_size)
                           .offset((page - 1) * page_size)).all()
    read_ids = set(session.execute(read.where(AlertRead.alert_id.in_([a.id for a, _ in rows]))).scalars())
    unread = session.execute(select(func.count()).select_from(Alert).where(Alert.id.not_in(read))).scalar_one()
    return rows, total, read_ids, unread


def mark_read(session: Session, user_id: str, alert_ids: list[str]) -> int:
    existing = set(session.execute(select(AlertRead.alert_id).where(AlertRead.user_id == user_id,
                                                                    AlertRead.alert_id.in_(alert_ids))).scalars())
    new = [aid for aid in alert_ids if aid not in existing]
    for aid in new:
        session.add(AlertRead(alert_id=aid, user_id=user_id))
    session.commit()
    return len(new)
