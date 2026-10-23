"""Issuer verification behind a replaceable adapter interface.

Only ``MockIssuerAdapter`` exists. It compares extracted fields with explicitly configured SYNTHETIC reference
records (``issuer_reference_records``); it performs no network access and contacts no authority. A
"simulated_match" means only that the extracted fields equal a configured demo record. Without a configured
reference, the outcome is ``manual_review`` — a match is never manufactured. Reference values are never
returned, so other institutions' data cannot leak through a mismatch.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Document, ExtractedField, IssuerReferenceRecord, VerificationAttempt
from app.models.enums import DocumentCategory, FieldStatus, ReferenceAvailability, VerificationOutcome as V
from app.services import processing as processing_service
from app.services.normalize import is_grounded, normalize_identifier, text_similarity

SIMULATION_LABEL = "SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY"
NAME_MATCH_THRESHOLD = 0.9


@dataclass
class VerificationRequest:
    category: DocumentCategory
    certificate_number: str | None
    institution_name: str | None
    issue_date: str | None  # ISO, only when unambiguous
    issuing_authority: str | None


@dataclass
class VerificationResult:
    outcome: V
    explanation: str
    fields_compared: list[dict] = field(default_factory=list)
    reference_code: str | None = None


class IssuerVerificationAdapter(Protocol):
    name: str
    method: str
    simulated: bool

    def verify(self, session: Session, request: VerificationRequest, today: date) -> VerificationResult: ...


class MockIssuerAdapter:
    name = "mock_synthetic_registry"
    method = "simulated_reference_lookup"
    simulated = True
    supported = frozenset({DocumentCategory.FIRE_SAFETY_CERTIFICATE, DocumentCategory.OCCUPANCY_CERTIFICATE,
                           DocumentCategory.COMPLETION_CERTIFICATE,
                           DocumentCategory.STRUCTURAL_STABILITY_CERTIFICATE})

    def verify(self, session: Session, request: VerificationRequest, today: date) -> VerificationResult:
        if request.category not in self.supported:
            return VerificationResult(V.UNSUPPORTED, f"The simulated registry does not cover "
                                      f"'{request.category.value}' documents.")
        if not request.certificate_number:
            return VerificationResult(V.MANUAL_REVIEW, "No reliably extracted certificate number to look up; "
                                      "manual review required.")
        ref = session.execute(
            select(IssuerReferenceRecord).where(
                IssuerReferenceRecord.document_category == request.category,
                IssuerReferenceRecord.certificate_number_normalized == normalize_identifier(request.certificate_number),
            )
        ).scalar_one_or_none()
        if ref is None:
            return VerificationResult(V.MANUAL_REVIEW, "No synthetic reference record is configured for this "
                                      "certificate number. Nothing was verified; manual review required.",
                                      [{"field": "certificate_number", "document_value": request.certificate_number,
                                        "result": "no_reference"}])
        if ref.availability == ReferenceAvailability.UNAVAILABLE:
            return VerificationResult(V.SIMULATED_UNAVAILABLE, "The simulated registry reports this record as "
                                      "unavailable. Nothing was verified.", reference_code=ref.reference_code)

        compared = [{"field": "certificate_number", "document_value": request.certificate_number, "result": "match"}]
        compared.append(_compare_text("institution_name", request.institution_name, ref.institution_name))
        compared.append(_compare_text("issuing_authority", request.issuing_authority, ref.issuing_authority))
        if request.issue_date and ref.issue_date:
            compared.append({"field": "issue_date", "document_value": request.issue_date,
                             "result": "match" if request.issue_date == ref.issue_date else "mismatch"})
        else:
            compared.append({"field": "issue_date", "document_value": request.issue_date, "result": "not_available"})

        mismatched = [c["field"] for c in compared if c["result"] == "mismatch"]
        if mismatched:
            return VerificationResult(V.SIMULATED_MISMATCH, "The synthetic reference record differs on: "
                                      f"{', '.join(mismatched)}. This is a simulated comparison only.",
                                      compared, ref.reference_code)
        if compared[1]["result"] != "match":
            return VerificationResult(V.MANUAL_REVIEW, "The institution name could not be compared reliably; "
                                      "manual review required.", compared, ref.reference_code)
        if ref.valid_until and ref.valid_until < today.isoformat():
            return VerificationResult(V.SIMULATED_EXPIRED, f"The synthetic reference record's validity ended on "
                                      f"{ref.valid_until}. This is a simulated comparison only.",
                                      compared, ref.reference_code)
        return VerificationResult(V.SIMULATED_MATCH, "The extracted fields match a configured synthetic reference "
                                  "record. This does not establish authenticity.", compared, ref.reference_code)


def _compare_text(name: str, document_value: str | None, reference_value: str) -> dict:
    if not document_value:
        return {"field": name, "document_value": None, "result": "not_available"}
    result = "match" if text_similarity(document_value, reference_value) >= NAME_MATCH_THRESHOLD else "mismatch"
    return {"field": name, "document_value": document_value, "result": result}


ADAPTER: IssuerVerificationAdapter = MockIssuerAdapter()


def _usable(fields: list[ExtractedField], name: str, pages: dict[int, str]) -> ExtractedField | None:
    for f in fields:
        if f.field_name == name and f.status == FieldStatus.EXTRACTED and is_grounded(f.evidence_quote,
                                                                                       pages.get(f.page_number, "")):
            return f
    return None


def verify_document(session: Session, document: Document, today: date,
                    adapter: IssuerVerificationAdapter = ADAPTER) -> VerificationAttempt:
    processing = processing_service.get_processing(session, document.id)
    if not processing_service.is_current(processing, document) or processing.status.value == "failed":
        raise AppError(409, "document_not_processed",
                       "Process the document successfully before requesting a simulated issuer check.")
    pages = {p.page_number: p.text for p in processing.pages}
    get = lambda n: _usable(processing.fields, n, pages)  # noqa: E731
    issue = get("issue_date")
    request = VerificationRequest(
        category=document.category,
        certificate_number=(f := get("certificate_number")) and f.raw_value,
        institution_name=(f := get("institution_name")) and f.raw_value,
        issue_date=(issue.normalized_value or {}).get("date") if issue else None,
        issuing_authority=(f := get("issuing_authority")) and f.raw_value,
    )
    result = adapter.verify(session, request, today)
    attempt = VerificationAttempt(
        application_id=document.application_id, document_id=document.id,
        document_filename=document.original_filename, adapter=adapter.name, method=adapter.method,
        simulated=adapter.simulated, outcome=result.outcome, explanation=result.explanation,
        fields_compared=result.fields_compared, reference_code=result.reference_code,
    )
    session.add(attempt)
    session.commit()
    return attempt


def latest_attempts(session: Session, application_id: str) -> dict[str, VerificationAttempt]:
    rows = session.execute(
        select(VerificationAttempt).where(VerificationAttempt.application_id == application_id)
        .order_by(VerificationAttempt.created_at, VerificationAttempt.id)
    ).scalars().all()
    latest: dict[str, VerificationAttempt] = {}
    for row in rows:
        if row.document_id:
            latest[row.document_id] = row
    return latest
