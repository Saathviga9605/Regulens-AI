"""Reviewer queue: per-application review summary built from each application's latest scrutiny run.

Computed in Python over all applications (adequate for the prototype's scale; a materialised summary would be
needed for large volumes). Counts are derived from persisted findings and evidence requests only.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Application, EvidenceRequest, Finding, ScrutinyRun
from app.models.enums import ApplicationStatus, EvidenceRequestStatus, FindingKind, ReviewStatus, Severity
from app.services.review import UNRESOLVED


@dataclass
class QueueRow:
    application: Application
    latest_run: ScrutinyRun | None
    unresolved_by_severity: dict = field(default_factory=dict)
    unresolved_total: int = 0
    findings_total: int = 0
    reviewed_total: int = 0
    open_requests: int = 0
    overdue_requests: int = 0

    @property
    def review_state(self) -> str:
        if self.latest_run is None:
            return "no_scrutiny"
        if self.findings_total == 0 or self.unresolved_total == 0:
            return "complete"
        return "in_progress" if self.reviewed_total else "not_started"


def build_rows(session: Session) -> list[QueueRow]:
    apps = session.execute(select(Application).options(joinedload(Application.institution))).unique().scalars().all()
    runs: dict[str, ScrutinyRun] = {}
    for run in session.execute(select(ScrutinyRun).order_by(ScrutinyRun.run_number)).scalars():
        runs[run.application_id] = run  # last one wins = latest
    latest_ids = {r.id for r in runs.values()}
    findings = session.execute(select(Finding).where(Finding.run_id.in_(latest_ids))).scalars().all() if latest_ids else []
    requests = session.execute(select(EvidenceRequest).where(EvidenceRequest.status == EvidenceRequestStatus.OPEN)).scalars().all()
    today = date.today().isoformat()
    rows = {a.id: QueueRow(a, runs.get(a.id)) for a in apps}
    for f in findings:
        row = rows[f.application_id]
        row.findings_total += 1
        if f.review_status in UNRESOLVED and not (f.kind == FindingKind.ANOMALY_INDICATOR and f.severity == Severity.INFO):
            row.unresolved_total += 1
            row.unresolved_by_severity[f.severity.value] = row.unresolved_by_severity.get(f.severity.value, 0) + 1
        if f.review_status != ReviewStatus.NOT_REVIEWED:
            row.reviewed_total += 1
    for r in requests:
        rows[r.application_id].open_requests += 1
        if r.due_date and r.due_date < today:
            rows[r.application_id].overdue_requests += 1
    return list(rows.values())


def query(session: Session, *, q: str | None, status: ApplicationStatus | None, scrutiny_status: str | None,
          severity: Severity | None, unresolved_only: bool, review_state: str | None, sort: str):
    rows = build_rows(session)
    counts = {
        "pending_review": sum(1 for r in rows if r.unresolved_total > 0),
        "unresolved_high": sum(r.unresolved_by_severity.get("high", 0) for r in rows),
        "awaiting_additional_evidence": sum(1 for r in rows if r.open_requests > 0
                                            or r.application.status == ApplicationStatus.AWAITING_ADDITIONAL_EVIDENCE),
        "completed_preliminary_reviews": sum(1 for r in rows
                                             if r.application.status == ApplicationStatus.PRELIMINARY_SCRUTINY_COMPLETED),
        "no_scrutiny_yet": sum(1 for r in rows if r.latest_run is None),
    }
    if q:
        needle = q.strip().casefold()
        rows = [r for r in rows if needle in r.application.application_code.casefold()
                or needle in r.application.institution.name.casefold()
                or needle in r.application.institution.institution_code.casefold()
                or needle in r.application.institution.state.casefold()]
    if status:
        rows = [r for r in rows if r.application.status == status]
    if scrutiny_status:
        rows = [r for r in rows if (r.latest_run.status.value if r.latest_run else "none") == scrutiny_status]
    if severity:
        rows = [r for r in rows if r.unresolved_by_severity.get(severity.value, 0) > 0]
    if unresolved_only:
        rows = [r for r in rows if r.unresolved_total > 0]
    if review_state:
        rows = [r for r in rows if r.review_state == review_state]
    order = ["high", "medium", "low", "info"]
    if sort == "application_code":
        rows.sort(key=lambda r: r.application.application_code)
    elif sort == "updated":
        rows.sort(key=lambda r: (r.application.updated_at, r.application.application_code), reverse=True)
    else:  # priority: most unresolved high, then medium..., overdue requests, then code (stable)
        rows.sort(key=lambda r: tuple(-r.unresolved_by_severity.get(s, 0) for s in order)
                  + (-r.overdue_requests, -r.unresolved_total, r.application.application_code))
    return rows, counts


def severity_counter(findings: list[Finding]) -> dict:
    return dict(Counter(f.severity.value for f in findings))
