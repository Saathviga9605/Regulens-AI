"""Deterministic preliminary scrutiny engine.

A run (1) processes documents whose results are missing or stale, (2) snapshots the enabled rules, (3) evaluates
each rule into pass / issue / inconclusive / not_applicable evaluations, (4) runs anomaly detectors, and
(5) persists evaluations and findings. Findings are created for ``issue`` and ``inconclusive`` evaluations and for
anomaly indicators. Nothing here approves, rejects, or labels a document fraudulent.

Evidence use: a field is *usable* only if its status is ``extracted`` and its evidence quote is re-verified against
the stored page text. Ambiguous/unverified fields lead to ``inconclusive``, never to a conflict. A field missing
from one document is never a conflict. Same inputs + same rule versions → same results.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.types import utcnow
from app.models import (
    Application,
    Document,
    DocumentProcessing,
    ExtractedField,
    Finding,
    RuleEvaluation,
    ScrutinyRule,
    ScrutinyRun,
)
from app.models.enums import (
    AuditOutcome,
    DocumentCategory,
    DocumentStatus,
    FieldStatus,
    FindingKind,
    InstitutionType,
    ProcessingStatus,
    ReviewStatus,
    RuleOutcome as O,
    RuleType,
    RunStatus,
    Severity,
    VerificationOutcome,
)
from app.services import issuer_verification, processing as processing_service
from app.services import alerts, audit
from app.services import aph_demo_ruleset
from app.services.applications import get_application
from app.services.documents import other_application_matches
from app.services.normalize import is_grounded, normalize_identifier, normalize_name, text_similarity
from app.services.storage import DocumentStorage

logger = logging.getLogger("regulens.scrutiny")

STALE_RUN_AFTER = timedelta(minutes=15)
EVALUATOR_VERSION = "2"
LABELS = {c: c.value.replace("_", " ") for c in DocumentCategory}


# --- Context ---------------------------------------------------------------------------------------

@dataclass
class DocCtx:
    document: Document
    processing: DocumentProcessing | None
    pages: dict[int, str]
    fields: dict[str, ExtractedField]
    other_app_matches: int = 0

    @property
    def label(self) -> str:
        return self.document.original_filename

    @property
    def is_copy(self) -> bool:
        return self.document.status == DocumentStatus.DUPLICATE_DETECTED

    def field(self, name: str) -> ExtractedField | None:
        return self.fields.get(name)

    def usable(self, name: str) -> ExtractedField | None:
        f = self.fields.get(name)
        if f and f.status == FieldStatus.EXTRACTED and is_grounded(f.evidence_quote, self.pages.get(f.page_number, "")):
            return f
        return None

    def processed_ok(self) -> bool:
        return self.processing is not None and self.processing.status != ProcessingStatus.FAILED


@dataclass
class Ctx:
    application: Application
    institution: dict
    documents: list[DocCtx]
    scrutiny_date: date | None
    scrutiny_date_source: str
    verifications: dict

    def of_category(self, category: DocumentCategory) -> list[DocCtx]:
        return [d for d in self.documents if d.document.category == category]

    def originals(self) -> list[DocCtx]:
        return [d for d in self.documents if not d.is_copy]


def _institution_view(application: Application) -> dict:
    """Use the institution details frozen with the application if present, else the live record."""
    snap = application.institution_snapshot
    inst = application.institution
    return {
        "source": "snapshot captured when the application was marked ready" if snap else "current institution record",
        "name": (snap or {}).get("name", inst.name),
        "trust_name": (snap or {}).get("trust_name", inst.trust_name),
        "address": (snap or {}).get("address", inst.address),
        "property_identifier": (snap or {}).get("property_identifier", inst.property_identifier),
    }


def build_context(session: Session, application: Application, scrutiny_date: date | None,
                  scrutiny_date_source: str = "unavailable") -> Ctx:
    docs = session.execute(
        select(Document).where(Document.application_id == application.id,
                               Document.status != DocumentStatus.INTAKE_FAILED)
        .order_by(Document.uploaded_at, Document.id)
    ).scalars().all()
    matches = other_application_matches(session, list(docs))
    contexts = []
    for d in docs:
        processing = processing_service.get_processing(session, d.id)
        if not processing_service.is_current(processing, d):
            processing = None
        pages = {p.page_number: p.text for p in processing.pages} if processing else {}
        fields = {f.field_name: f for f in processing.fields} if processing else {}
        contexts.append(DocCtx(d, processing, pages, fields, matches.get(d.id, 0)))
    return Ctx(application, _institution_view(application), contexts, scrutiny_date, scrutiny_date_source,
               issuer_verification.latest_attempts(session, application.id))


# --- Evaluation helpers ----------------------------------------------------------------------------

@dataclass
class Eval:
    subject_key: str
    outcome: O
    explanation: str
    title: str
    finding_type: str
    document_ids: list[str] = field(default_factory=list)
    field_ids: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    compared_values: list[dict] = field(default_factory=list)
    missing_evidence: str | None = None


def _ev(doc: DocCtx, f: ExtractedField) -> dict:
    return {"document_id": doc.document.id, "document_filename": doc.label, "field_id": f.id,
            "field_name": f.field_name, "value": f.raw_value, "page_number": f.page_number,
            "quote": f.evidence_quote}


def _doc_ref(doc: DocCtx) -> dict:
    return {"document_id": doc.document.id, "document_filename": doc.label, "field_id": None, "field_name": None,
            "value": None, "page_number": None, "quote": None}


def _unprocessed(doc: DocCtx, subject: str, rule_title: str) -> Eval:
    reason = (doc.processing.failure_reason if doc.processing else None) or "The document has not been processed."
    return Eval(subject, O.INCONCLUSIVE, f"'{doc.label}' could not be evaluated: {reason}",
                f"{rule_title}: not evaluable for {doc.label}", "insufficient_evidence", [doc.document.id],
                evidence=[_doc_ref(doc)], missing_evidence="Readable extracted text for this document.")


def _has_unreadable_pages(doc: DocCtx) -> bool:
    return doc.processing is not None and any(p.status.value != "ok" for p in doc.processing.pages)


# --- Rule evaluators -------------------------------------------------------------------------------

def eval_expected_document(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    category = DocumentCategory(p["category"])
    label = LABELS[category]
    types = p.get("application_types")
    if types and ctx.application.application_type.value not in types:
        return [Eval("application", O.NOT_APPLICABLE, f"Applies only to application types {', '.join(types)}.",
                     rule.title, "expected_document")]
    present = ctx.of_category(category)
    if present:
        return [Eval("application", O.PASS, f"{len(present)} document(s) uploaded as {label}.", rule.title,
                     "expected_document", [d.document.id for d in present], evidence=[_doc_ref(d) for d in present])]
    predicted = [d for d in ctx.documents if d.processing and d.processing.predicted_category == category]
    if predicted:
        names = ", ".join(f"'{d.label}'" for d in predicted)
        return [Eval("application", O.INCONCLUSIVE,
                     f"No document was uploaded as {label}, but the text of {names} resembles one. "
                     "Check the selected category.", f"{rule.title}: possibly miscategorised", "expected_document",
                     [d.document.id for d in predicted], evidence=[_doc_ref(d) for d in predicted])]
    return [Eval("application", O.ISSUE, f"No document categorised as {label} has been uploaded.",
                 f"Expected document not found: {label}", "missing_document",
                 missing_evidence=f"A document uploaded with the category '{label}'.")]


def _elapsed_years(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(year=start.year + years, day=28)


def _date_field(doc: DocCtx, field_name: str) -> tuple[ExtractedField | None, date | None]:
    field = doc.field(field_name)
    normalized = _date_of(doc.usable(field_name))
    try:
        return field, date.fromisoformat(normalized) if normalized else None
    except ValueError:
        return field, None


def eval_validity_period(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    category = DocumentCategory(p["category"])
    docs = [doc for doc in ctx.originals() if doc.document.category == category]
    if not docs:
        return [Eval("application", O.NOT_APPLICABLE, f"No {LABELS[category]} uploaded.", rule.title,
                     "validity_period")]
    results = []
    for doc in docs:
        subject = f"document:{doc.document.id}"
        source_field, issue_date = _date_field(doc, p["start_field"])
        if not doc.processed_ok():
            results.append(_unprocessed(doc, subject, rule.title))
        elif source_field is None or issue_date is None:
            results.append(Eval(
                subject, O.INCONCLUSIVE,
                f"The issue date needed to assess the stated {p['years']}-year period in '{doc.label}' "
                "is missing or unreadable.",
                f"{rule.title}: issue date needs review", "validity_period", [doc.document.id],
                [source_field.id] if source_field else [], [_ev(doc, source_field)] if source_field else [],
                missing_evidence="An unambiguous, grounded issue date and an available reference date.",
            ))
        elif ctx.scrutiny_date is None:
            results.append(Eval(
                subject, O.INCONCLUSIVE, "The scrutiny reference date is unavailable, so the validity period "
                "cannot be assessed.", f"{rule.title}: reference date unavailable", "validity_period",
                [doc.document.id], [source_field.id], [_ev(doc, source_field)],
                [{"source": "reference_date", "value": None, "date_source": ctx.scrutiny_date_source}],
                "A scrutiny reference date derived from the application or explicitly supplied by an operator.",
            ))
        else:
            expiry = _elapsed_years(issue_date, p["years"])
            outcome = O.ISSUE if ctx.scrutiny_date > expiry else O.PASS
            explanation = (f"The stated {p['years']}-year period from {issue_date.isoformat()} ends on "
                           f"{expiry.isoformat()}; the reference date is {ctx.scrutiny_date.isoformat()}.")
            results.append(Eval(
                subject, outcome, explanation, rule.title if outcome == O.PASS else f"{rule.title}: period elapsed",
                "validity_period", [doc.document.id], [source_field.id], [_ev(doc, source_field)],
                [{"source": "issue_date", "value": issue_date.isoformat()},
                 {"source": "calculated_period_end", "value": expiry.isoformat()},
                 {"source": "reference_date", "value": ctx.scrutiny_date.isoformat(),
                  "date_source": ctx.scrutiny_date_source}],
            ))
    return results


def eval_conditional_document(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    required = DocumentCategory(p["required_category"])
    trigger = DocumentCategory(p["trigger_category"])
    triggers = [doc for doc in ctx.originals() if doc.document.category == trigger]
    if not triggers:
        return [Eval("application", O.INCONCLUSIVE, f"No {LABELS[trigger]} is available to assess the "
                     "condition that may require this document.", f"{rule.title}: trigger evidence unavailable",
                     "conditional_document", missing_evidence=f"A readable {LABELS[trigger]} issue date.")]
    if ctx.scrutiny_date is None:
        return [Eval("application", O.INCONCLUSIVE, "The scrutiny reference date is unavailable, so the "
                     "condition cannot be assessed.", f"{rule.title}: reference date unavailable",
                     "conditional_document", missing_evidence="A scrutiny reference date.")]
    if ctx.scrutiny_date_source != p["reference_date_source"]:
        return [Eval(
            "application", O.INCONCLUSIVE,
            f"The rule requires a reference date from {p['reference_date_source']}, but the available date is "
            f"from {ctx.scrutiny_date_source}.",
            f"{rule.title}: reference date source needs review", "conditional_document",
            missing_evidence=f"A reference date sourced from {p['reference_date_source']}.",
        )]
    out = []
    for doc in triggers:
        subject = f"document:{doc.document.id}"
        source_field, trigger_date = _date_field(doc, p["trigger_field"])
        if not doc.processed_ok() or trigger_date is None:
            out.append(Eval(
                subject, O.INCONCLUSIVE, f"The trigger date in '{doc.label}' is missing or unreadable.",
                f"{rule.title}: trigger date needs review", "conditional_document", [doc.document.id],
                [source_field.id] if source_field else [], [_ev(doc, source_field)] if source_field else [],
                missing_evidence="A grounded, unambiguous trigger date.",
            ))
            continue
        due_date = _elapsed_years(trigger_date, p["years_elapsed"])
        condition_met = (ctx.scrutiny_date >= due_date if p["comparison"] == "at_least"
                         else ctx.scrutiny_date > due_date)
        if not condition_met:
            out.append(Eval(subject, O.NOT_APPLICABLE,
                            f"The condition is not met: the {p['comparison'].replace('_', ' ')} "
                            f"{p['years_elapsed']}-year threshold from {trigger_date.isoformat()} is "
                            f"{due_date.isoformat()}.",
                            rule.title, "conditional_document", [doc.document.id], [source_field.id],
                            [_ev(doc, source_field)]))
            continue
        required_docs = ctx.of_category(required)
        if required_docs:
            out.append(Eval(subject, O.PASS, f"The condition is met and a {LABELS[required]} is present.",
                            rule.title, "conditional_document",
                            [doc.document.id, *[item.document.id for item in required_docs]],
                            [source_field.id], [_ev(doc, source_field), *[_doc_ref(item) for item in required_docs]],
                            [{"source": "condition_due_date", "value": due_date.isoformat()},
                             {"source": "reference_date", "value": ctx.scrutiny_date.isoformat(),
                              "date_source": ctx.scrutiny_date_source}]))
        else:
            out.append(Eval(subject, O.ISSUE, f"The condition is met, but no {LABELS[required]} is present.",
                            f"{rule.title}: required document not found", "conditional_document",
                            [doc.document.id], [source_field.id], [_ev(doc, source_field)],
                            [{"source": "condition_due_date", "value": due_date.isoformat()},
                             {"source": "reference_date", "value": ctx.scrutiny_date.isoformat(),
                              "date_source": ctx.scrutiny_date_source}],
                            f"A {LABELS[required]} because the stated condition is met."))
    return out


def eval_alternative_document_group(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    categories = [DocumentCategory(value) for value in p["categories"]]
    labels = [LABELS[category] for category in categories]
    application_types = p["application_types"]
    if ctx.application.application_type.value not in application_types:
        return [Eval(
            "application", O.NOT_APPLICABLE,
            f"Applies only to application types {', '.join(application_types)}.",
            rule.title, "alternative_document_group",
        )]

    documents = [doc for category in categories for doc in ctx.originals()
                 if doc.document.category == category]
    if not documents:
        predicted = [doc for doc in ctx.documents if doc.processing and
                     doc.processing.predicted_category in categories]
        if predicted:
            return [Eval(
                "application", O.INCONCLUSIVE,
                "No accepted alternative was uploaded under its category, but one or more documents "
                "may match; verify their document types.",
                f"{rule.title}: document type needs review", "alternative_document_group",
                [doc.document.id for doc in predicted],
                evidence=[_doc_ref(doc) for doc in predicted],
                missing_evidence=f"One of: {', '.join(labels)}.",
            )]
        return [Eval(
            "application", O.ISSUE,
            f"None of the accepted alternatives was uploaded: {', '.join(labels)}.",
            f"{rule.title}: no accepted alternative found", "missing_document",
            missing_evidence=f"One valid document from: {', '.join(labels)}.",
        )]

    if (p["validity_reference"] != "operator_override" or
            ctx.scrutiny_date_source != "operator_override" or ctx.scrutiny_date is None):
        return [Eval(
            "application", O.INCONCLUSIVE,
            "An accepted document is present, but its validity cannot be assessed without an explicitly "
            "supplied operator reference date.",
            f"{rule.title}: validity date needs review", "alternative_document_group",
            [doc.document.id for doc in documents],
            evidence=[_doc_ref(doc) for doc in documents],
            compared_values=[{"source": "reference_date", "value": ctx.scrutiny_date.isoformat()
                              if ctx.scrutiny_date else None,
                              "date_source": ctx.scrutiny_date_source}],
            missing_evidence="An explicit operator-supplied reference date and a grounded validity end date.",
        )]

    evidence: list[dict] = []
    document_ids: list[str] = []
    field_ids: list[str] = []
    compared_values: list[dict] = []
    has_valid = False
    has_unknown_validity = False
    for doc in documents:
        validity_field, valid_until = _date_field(doc, "valid_until")
        document_ids.append(doc.document.id)
        if not doc.processed_ok() or validity_field is None or valid_until is None:
            has_unknown_validity = True
            evidence.append(_ev(doc, validity_field) if validity_field else _doc_ref(doc))
            continue
        field_ids.append(validity_field.id)
        evidence.append(_ev(doc, validity_field))
        compared_values.append({"source": "valid_until", "document_id": doc.document.id,
                                "value": valid_until.isoformat()})
        has_valid = has_valid or valid_until >= ctx.scrutiny_date

    compared_values.append({"source": "reference_date", "value": ctx.scrutiny_date.isoformat(),
                            "date_source": ctx.scrutiny_date_source})
    if has_valid:
        outcome = O.PASS
        explanation = "At least one accepted alternative has a grounded validity date that includes the " \
                      f"explicit operator reference date {ctx.scrutiny_date.isoformat()}."
        title = rule.title
        missing_evidence = None
    elif has_unknown_validity:
        outcome = O.INCONCLUSIVE
        explanation = "No accepted alternative could be confirmed valid because one or more validity dates " \
                      "are missing, unreadable, or ambiguous."
        title = f"{rule.title}: validity needs review"
        missing_evidence = "A grounded, unambiguous valid-until date for at least one accepted alternative."
    else:
        outcome = O.ISSUE
        explanation = "Every uploaded accepted alternative has an expired validity date as of the explicit " \
                      f"operator reference date {ctx.scrutiny_date.isoformat()}."
        title = f"{rule.title}: no currently valid alternative"
        missing_evidence = "At least one accepted alternative with current validity."
    return [Eval("application", outcome, explanation, title, "alternative_document_group",
                 document_ids, field_ids, evidence, compared_values, missing_evidence)]


def _demo_aph_fire_safety(rule, ctx: Ctx) -> list[Eval]:
    present = ctx.of_category(DocumentCategory.FIRE_SAFETY_CERTIFICATE)
    if not present:
        return eval_expected_document(rule, rule.parameters, ctx)

    results = []
    for doc in present:
        subject = f"document:{doc.document.id}"
        if not doc.processed_ok():
            results.append(_unprocessed(doc, subject, rule.title))
            continue
        validity_field, valid_until = _date_field(doc, "valid_until")
        if validity_field is None or valid_until is None:
            results.append(Eval(
                subject, O.INCONCLUSIVE,
                f"The stated validity of '{doc.label}' is missing or unreadable.",
                f"{rule.title}: validity needs review", "validity_period", [doc.document.id],
                [validity_field.id] if validity_field else [],
                [_ev(doc, validity_field)] if validity_field else [_doc_ref(doc)],
                missing_evidence="A grounded, unambiguous validity end date.",
            ))
        elif ctx.scrutiny_date is None:
            results.append(Eval(
                subject, O.INCONCLUSIVE,
                "The application submission date is unavailable, so the stated validity cannot be assessed.",
                f"{rule.title}: submission date unavailable", "validity_period", [doc.document.id],
                [validity_field.id], [_ev(doc, validity_field)],
                missing_evidence="The application submission date.",
            ))
        elif valid_until < ctx.scrutiny_date:
            results.append(Eval(
                subject, O.ISSUE,
                f"'{doc.label}' states validity until {valid_until.isoformat()}, before the application "
                f"submission date {ctx.scrutiny_date.isoformat()}.",
                f"{rule.title}: stated validity ended", "expired_validity", [doc.document.id],
                [validity_field.id], [_ev(doc, validity_field)],
                [{"source": "stated_valid_until", "value": valid_until.isoformat()},
                 {"source": "application_submission_date", "value": ctx.scrutiny_date.isoformat()}],
            ))
        else:
            results.append(Eval(
                subject, O.INCONCLUSIVE,
                f"'{doc.label}' states validity through {valid_until.isoformat()}, but the issuing authority "
                "has not been independently verified.",
                f"{rule.title}: issuer requires human review", "validity_period", [doc.document.id],
                [validity_field.id], [_ev(doc, validity_field)],
                [{"source": "stated_valid_until", "value": valid_until.isoformat()},
                 {"source": "application_submission_date", "value": ctx.scrutiny_date.isoformat()}],
                "Independent verification that the issuer is a competent authority.",
            ))
    return results


def _demo_aph_alternative_group(rule, ctx: Ctx) -> list[Eval]:
    p = rule.parameters
    categories = [DocumentCategory(category) for category in p["categories"]]
    labels = [LABELS[category] for category in categories]
    if ctx.application.application_type.value not in p["application_types"]:
        return [Eval("application", O.NOT_APPLICABLE, "This application type is outside the demo rule scope.",
                     rule.title, "alternative_document_group")]

    documents = [doc for category in categories for doc in ctx.originals()
                 if doc.document.category == category]
    if not documents:
        predicted = [doc for doc in ctx.documents if doc.processing and
                     doc.processing.predicted_category in categories]
        if predicted:
            return [Eval(
                "application", O.INCONCLUSIVE,
                "No accepted alternative was uploaded under its category, but one or more documents may match; "
                "verify their document types.",
                f"{rule.title}: document type needs review", "alternative_document_group",
                [doc.document.id for doc in predicted],
                evidence=[_doc_ref(doc) for doc in predicted],
                missing_evidence=f"One of: {', '.join(labels)}.",
            )]
        return [Eval(
            "application", O.ISSUE,
            f"None of the accepted alternatives was uploaded: {', '.join(labels)}.",
            f"{rule.title}: no accepted alternative found", "missing_document",
            missing_evidence=f"One valid document from: {', '.join(labels)}.",
        )]

    evidence = []
    document_ids = []
    field_ids = []
    compared_values = []
    expired_count = 0
    unclear_count = 0
    for doc in documents:
        document_ids.append(doc.document.id)
        validity_field, valid_until = _date_field(doc, "valid_until")
        if not doc.processed_ok() or validity_field is None or valid_until is None:
            unclear_count += 1
            evidence.append(_ev(doc, validity_field) if validity_field else _doc_ref(doc))
            continue
        field_ids.append(validity_field.id)
        evidence.append(_ev(doc, validity_field))
        compared_values.append({"source": "stated_valid_until", "document_id": doc.document.id,
                                "value": valid_until.isoformat()})
        if ctx.scrutiny_date is not None and valid_until < ctx.scrutiny_date:
            expired_count += 1
        else:
            unclear_count += 1

    if ctx.scrutiny_date is None:
        outcome = O.INCONCLUSIVE
        explanation = "The application submission date is unavailable, so the validity of the alternatives " \
                      "cannot be assessed."
        title = f"{rule.title}: submission date unavailable"
        missing_evidence = "The application submission date and a grounded validity end date."
    elif expired_count == len(documents) and unclear_count == 0:
        outcome = O.ISSUE
        explanation = "Every uploaded accepted alternative states a validity end date before the application " \
                      f"submission date {ctx.scrutiny_date.isoformat()}."
        title = f"{rule.title}: no currently valid alternative"
        missing_evidence = "At least one alternative whose stated validity covers the submission date."
    else:
        outcome = O.INCONCLUSIVE
        explanation = "At least one accepted alternative is present, but its validity and/or issuing authority " \
                      "cannot be fully verified from the available evidence."
        title = f"{rule.title}: alternative needs human review"
        missing_evidence = "A grounded validity period and human verification of the competent authority."
    compared_values.append({"source": "application_submission_date",
                            "value": ctx.scrutiny_date.isoformat() if ctx.scrutiny_date else None,
                            "date_source": ctx.scrutiny_date_source})
    return [Eval("application", outcome, explanation, title, "alternative_document_group", document_ids,
                 field_ids, evidence, compared_values, missing_evidence)]


def eval_issuer_authority(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    category = DocumentCategory(p["category"])
    state = ctx.application.institution.state
    expected = p["authority_directory"].get(state)
    if expected is None:
        return [Eval("application", O.INCONCLUSIVE,
                     f"No authority-directory entry is configured for {state}; issuer authority was not inferred.",
                     f"{rule.title}: authority coverage unknown", "issuer_authority",
                     missing_evidence=f"A verified authority-directory entry for {state}.")]
    out = []
    for doc in [item for item in ctx.originals() if item.document.category == category]:
        field = doc.usable("issuing_authority")
        subject = f"document:{doc.document.id}"
        if not field:
            out.append(Eval(subject, O.INCONCLUSIVE,
                            f"The issuing authority in '{doc.label}' is missing or unreadable.",
                            f"{rule.title}: issuer needs review", "issuer_authority", [doc.document.id],
                            [doc.field("issuing_authority").id] if doc.field("issuing_authority") else [],
                            [_ev(doc, doc.field("issuing_authority"))] if doc.field("issuing_authority") else [],
                            missing_evidence="A grounded issuing-authority field."))
            continue
        normalized_issuer = normalize_name(field.raw_value)
        matches = [authority for authority in expected if normalize_name(authority) == normalized_issuer]
        outcome = O.PASS if matches else O.ISSUE
        out.append(Eval(
            subject, outcome,
            (f"The stated issuer in '{doc.label}' matches a configured authority-directory entry for {state}."
             if matches else f"The stated issuer in '{doc.label}' does not match a configured authority entry for {state}; "
             "this is an inconsistency indicator and requires human review."),
            rule.title if matches else f"{rule.title}: issuer requires review", "issuer_authority",
            [doc.document.id], [field.id], [_ev(doc, field)],
            [{"source": "stated_issuer", "value": field.raw_value},
             {"source": "authority_directory", "value": expected, "jurisdiction": state}],
        ))
    return out or [Eval("application", O.NOT_APPLICABLE, f"No {LABELS[category]} uploaded.", rule.title,
                        "issuer_authority")]


def eval_required_field(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    category, name = DocumentCategory(p["category"]), p["field_name"]
    docs = [d for d in ctx.of_category(category) if not d.is_copy]
    if not docs:
        return [Eval("application", O.NOT_APPLICABLE, f"No {LABELS[category]} uploaded.", rule.title,
                     "missing_field")]
    out = []
    for d in docs:
        subject = f"document:{d.document.id}"
        if not d.processed_ok():
            out.append(_unprocessed(d, subject, rule.title))
            continue
        f = d.field(name)
        if d.usable(name):
            out.append(Eval(subject, O.PASS, f"'{name}' found in '{d.label}'.", rule.title, "missing_field",
                            [d.document.id], [f.id], [_ev(d, f)]))
        elif f and f.status in (FieldStatus.AMBIGUOUS, FieldStatus.UNVERIFIED, FieldStatus.EXTRACTED):
            out.append(Eval(subject, O.INCONCLUSIVE,
                            f"'{name}' in '{d.label}' is {f.status.value}: {' '.join(f.warnings) or 'needs review'}",
                            f"{rule.title}: unclear value in {d.label}", "unclear_field", [d.document.id], [f.id],
                            [_ev(d, f)]))
        elif _has_unreadable_pages(d):
            out.append(Eval(subject, O.INCONCLUSIVE,
                            f"'{name}' was not found in the readable text of '{d.label}', but some pages were "
                            "unreadable, so it may be present.", f"{rule.title}: not found in readable text",
                            "missing_field", [d.document.id], evidence=[_doc_ref(d)],
                            missing_evidence=f"A labelled '{name}' value."))
        else:
            out.append(Eval(subject, O.ISSUE, f"No labelled '{name}' value was found in '{d.label}'.",
                            f"Required field not found: {name} ({d.label})", "missing_field", [d.document.id],
                            evidence=[_doc_ref(d)], missing_evidence=f"A labelled '{name}' value in '{d.label}'."))
    return out


def eval_processing_quality(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    if not ctx.documents:
        return [Eval("application", O.NOT_APPLICABLE, "No documents uploaded.", rule.title, "processing")]
    out = []
    for d in ctx.documents:
        subject = f"document:{d.document.id}"
        proc = d.processing
        if proc is None:
            out.append(Eval(subject, O.ISSUE, f"'{d.label}' has not been processed.",
                            f"Document not processed: {d.label}", "processing_failed", [d.document.id],
                            evidence=[_doc_ref(d)]))
        elif proc.status == ProcessingStatus.FAILED:
            out.append(Eval(subject, O.ISSUE, f"Text extraction failed for '{d.label}': {proc.failure_reason}",
                            f"Unreadable document: {d.label}", "processing_failed", [d.document.id],
                            evidence=[_doc_ref(d)], missing_evidence="Machine-readable text; review manually."))
        elif proc.status == ProcessingStatus.COMPLETED_WITH_WARNINGS:
            bad = [str(pg.page_number) for pg in proc.pages if pg.status.value != "ok"]
            detail = f"pages {', '.join(bad)} unreadable" if bad else "OCR text or other warnings"
            out.append(Eval(subject, O.INCONCLUSIVE, f"'{d.label}' was processed with warnings ({detail}). "
                            "Extracted values may be incomplete.", f"Partially readable: {d.label}",
                            "processing_partial", [d.document.id], evidence=[_doc_ref(d)]))
        else:
            out.append(Eval(subject, O.PASS, f"'{d.label}' has readable text on all processed pages.", rule.title,
                            "processing", [d.document.id]))
    return out


def eval_classification(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    allowed = ("high",) if p.get("min_confidence") == "high" else ("high", "medium")
    out = []
    for d in ctx.originals():
        subject = f"document:{d.document.id}"
        if not d.processed_ok():
            continue
        proc, selected = d.processing, d.document.category
        signals = "; ".join(s["signal"] for s in proc.classification_signals) or "none"
        if proc.classification_confidence not in allowed or proc.predicted_category is None:
            out.append(Eval(subject, O.INCONCLUSIVE,
                            f"The type of '{d.label}' could not be determined confidently from its text "
                            f"(selected: {LABELS[selected]}).", f"Uncertain document type: {d.label}",
                            "classification_uncertain", [d.document.id], evidence=[_doc_ref(d)]))
        elif proc.predicted_category != selected:
            predicted = LABELS[proc.predicted_category]
            outcome = O.INCONCLUSIVE if selected == DocumentCategory.OTHER else O.ISSUE
            out.append(Eval(subject, outcome,
                            f"'{d.label}' was uploaded as {LABELS[selected]}, but its text indicates {predicted} "
                            f"({proc.classification_confidence} confidence; signals: {signals}). The selected "
                            "category was not changed.", f"Category mismatch: {d.label}", "classification_mismatch",
                            [d.document.id], evidence=[_doc_ref(d)],
                            compared_values=[{"source": "selected at upload", "value": selected.value},
                                             {"source": "predicted from text", "value": proc.predicted_category.value}]))
        else:
            out.append(Eval(subject, O.PASS, f"Text of '{d.label}' agrees with its selected category ({signals}).",
                            rule.title, "classification", [d.document.id]))
    return out or [Eval("application", O.NOT_APPLICABLE, "No processed documents to check.", rule.title,
                        "classification")]


def _similarity_outcome(score: float, p: dict) -> O:
    if score >= p["match_threshold"]:
        return O.PASS
    if score < p["conflict_threshold"]:
        return O.ISSUE
    return O.INCONCLUSIVE


def eval_institution_name(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    name, attr = p["field_name"], p["institution_attribute"]
    record_value = ctx.institution.get(attr)
    cats = set(p.get("categories") or [])
    out = []
    for d in ctx.originals():
        if cats and d.document.category.value not in cats:
            continue
        f = d.field(name)
        if f is None or f.status == FieldStatus.NOT_FOUND:
            continue  # absence in one document is not a conflict
        subject = f"document:{d.document.id}"
        usable = d.usable(name)
        compared = [{"source": f"'{d.label}' page {f.page_number}", "value": f.raw_value},
                    {"source": f"application {ctx.institution['source']} ({attr})", "value": record_value}]
        if not usable:
            out.append(Eval(subject, O.INCONCLUSIVE, f"The {name} in '{d.label}' is {f.status.value}; it was not "
                            "compared.", f"{rule.title}: unclear value in {d.label}", "unclear_field",
                            [d.document.id], [f.id], [_ev(d, f)], compared))
            continue
        score = text_similarity(usable.raw_value or "", record_value or "")
        outcome = _similarity_outcome(score, p)
        text = {O.PASS: "matches", O.ISSUE: "does not match", O.INCONCLUSIVE: "is similar to but not the same as"}
        out.append(Eval(subject, outcome,
                        f"'{usable.raw_value}' in '{d.label}' {text[outcome]} the {attr} on record "
                        f"('{record_value}'); similarity {score:.2f}.",
                        f"Name conflict with application record: {d.label}" if outcome == O.ISSUE else rule.title,
                        "name_conflict", [d.document.id], [usable.id], [_ev(d, usable)],
                        compared + [{"source": "similarity score", "value": score}]))
    return out or [Eval("application", O.NOT_APPLICABLE, f"No document states a {name}.", rule.title, "name_conflict")]


def eval_field_consistency(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    name, mode, attr = p["field_name"], p["comparison"], p.get("institution_attribute")
    cats = set(p.get("categories") or [])
    docs = [d for d in ctx.originals() if not cats or d.document.category.value in cats]
    usable = [(d, d.usable(name)) for d in docs if d.usable(name)]
    unclear = [(d, d.field(name)) for d in docs if d.field(name) and not d.usable(name)
               and d.field(name).status != FieldStatus.NOT_FOUND]
    out: list[Eval] = []

    def same(a: str, b: str) -> O:
        if mode == "identifier":
            return O.PASS if normalize_identifier(a) == normalize_identifier(b) else O.ISSUE
        return _similarity_outcome(text_similarity(a, b), p)

    # Across documents (pairwise, stable order).
    conflicts, inconclusive = [], []
    for (d1, f1), (d2, f2) in combinations(usable, 2):
        result = same(f1.raw_value, f2.raw_value)
        if result == O.ISSUE:
            conflicts.append((d1, f1, d2, f2))
        elif result == O.INCONCLUSIVE:
            inconclusive.append((d1, f1, d2, f2))
    if conflicts:
        involved_ids = {x.id for _, f1, _, f2 in conflicts for x in (f1, f2)}
        involved = [(d, f) for d, f in usable if f.id in involved_ids]  # stable document order, each once
        groups: dict[str, tuple[str, list[str]]] = {}  # comparison key -> (value as written, locations)
        for d, f in involved:
            key = normalize_identifier(f.raw_value) if mode == "identifier" else f.raw_value
            groups.setdefault(key, (f.raw_value, []))[1].append(f"'{d.label}' (p.{f.page_number})")
        values_text = "; ".join(f"'{value}' in {', '.join(where)}" for value, where in groups.values())
        out.append(Eval("across_documents", O.ISSUE,
                        f"The {name.replace('_', ' ')} differs between documents: {values_text}.",
                        f"Conflicting {name.replace('_', ' ')} across documents", "cross_document_conflict",
                        [d.document.id for d, _ in involved], [f.id for _, f in involved],
                        [_ev(d, f) for d, f in involved],
                        [{"source": f"'{d.label}' p.{f.page_number}", "value": f.raw_value} for d, f in usable]))
    elif inconclusive:
        out.append(Eval("across_documents", O.INCONCLUSIVE,
                        f"The {name} values are similar but not identical across documents; review them.",
                        f"{rule.title}: similar but not identical values", "cross_document_conflict",
                        sorted({d.document.id for d, _ in usable}), [f.id for _, f in usable],
                        [_ev(d, f) for d, f in usable],
                        [{"source": f"'{d.label}' p.{f.page_number}", "value": f.raw_value} for d, f in usable]))
    elif len(usable) >= 2:
        out.append(Eval("across_documents", O.PASS, f"{len(usable)} documents state the same {name}.", rule.title,
                        "cross_document_conflict", [d.document.id for d, _ in usable], [f.id for _, f in usable],
                        [_ev(d, f) for d, f in usable]))

    # Against the application record.
    record = ctx.institution.get(attr) if attr else None
    if record:
        for d, f in usable:
            if mode == "identifier":
                # Record identifiers are free-form (e.g. 'SYN-MH-PUN-S.No.101/2A'); containment counts as consistent,
                # otherwise the formats may simply differ, so the result is inconclusive rather than a conflict.
                outcome = O.PASS if normalize_identifier(f.raw_value) in normalize_identifier(record) else O.INCONCLUSIVE
                score = None
            else:
                score = text_similarity(f.raw_value, record)
                outcome = _similarity_outcome(score, p)
            explanation = (f"'{f.raw_value}' in '{d.label}' compared with the {attr} on record ('{record}')"
                           + (f"; similarity {score:.2f}." if score is not None else ".")
                           + {O.PASS: " Consistent.", O.ISSUE: " They differ.",
                              O.INCONCLUSIVE: " Not clearly the same; review."}[outcome])
            out.append(Eval(f"record:{d.document.id}", outcome, explanation,
                            f"{name.replace('_', ' ').capitalize()} differs from application record: {d.label}"
                            if outcome == O.ISSUE else f"{rule.title} ({d.label})", "record_conflict",
                            [d.document.id], [f.id], [_ev(d, f)],
                            [{"source": f"'{d.label}' p.{f.page_number}", "value": f.raw_value},
                             {"source": f"application {ctx.institution['source']} ({attr})", "value": record}]))

    if unclear:
        out.append(Eval("unclear_values", O.INCONCLUSIVE,
                        f"Some {name} values could not be used for comparison: "
                        + "; ".join(f"'{d.label}' ({f.status.value})" for d, f in unclear) + ".",
                        f"{rule.title}: unclear values", "unclear_field", [d.document.id for d, _ in unclear],
                        [f.id for _, f in unclear], [_ev(d, f) for d, f in unclear]))
    return out or [Eval("application", O.NOT_APPLICABLE, f"Fewer than two documents state a {name} and there is "
                        "no record value to compare with.", rule.title, "cross_document_conflict")]


def eval_area(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    name, tolerance = p["field_name"], p["tolerance_percent"]
    values, unclear = [], []
    for d in ctx.originals():
        f = d.usable(name)
        if f and (f.normalized_value or {}).get("value_sq_m") is not None:
            values.append((d, f, f.normalized_value["value_sq_m"]))
        elif d.field(name) and d.field(name).status != FieldStatus.NOT_FOUND:
            unclear.append((d, d.field(name)))
    compared = [{"source": f"'{d.label}' p.{f.page_number}", "value": f.raw_value, "value_sq_m": v}
                for d, f, v in values]
    out = []
    if len(values) >= 2:
        low, high = min(v for *_, v in values), max(v for *_, v in values)
        spread = (high - low) / low * 100 if low else float("inf")
        if spread > tolerance:
            out.append(Eval("across_documents", O.ISSUE,
                            "Built-up areas differ by " + f"{spread:.1f}% (tolerance {tolerance}%): "
                            + "; ".join(f"{f.raw_value} in '{d.label}' (= {v:,.1f} sq m)" for d, f, v in values) + ".",
                            "Conflicting built-up area across documents", "cross_document_conflict",
                            [d.document.id for d, *_ in values], [f.id for _, f, _ in values],
                            [_ev(d, f) for d, f, _ in values], compared))
        else:
            out.append(Eval("across_documents", O.PASS, f"Built-up areas agree within {tolerance}%.", rule.title,
                            "cross_document_conflict", [d.document.id for d, *_ in values],
                            [f.id for _, f, _ in values], [_ev(d, f) for d, f, _ in values], compared))
    if unclear:
        out.append(Eval("unclear_values", O.INCONCLUSIVE,
                        "Some area values could not be compared (unit missing/unrecognised or value unclear): "
                        + "; ".join(f"'{f.raw_value}' in '{d.label}'" for d, f in unclear) + ".",
                        f"{rule.title}: incomparable values", "unclear_field", [d.document.id for d, _ in unclear],
                        [f.id for _, f in unclear], [_ev(d, f) for d, f in unclear]))
    return out or [Eval("application", O.NOT_APPLICABLE, "Fewer than two comparable area values.", rule.title,
                        "cross_document_conflict")]


def _date_of(f: ExtractedField | None) -> str | None:
    return (f.normalized_value or {}).get("date") if f else None


def eval_date_order(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    start, end = p["start_field"], p["end_field"]
    out = []
    for d in ctx.originals():
        fs, fe = d.field(start), d.field(end)
        if not fs or not fe or FieldStatus.NOT_FOUND in (fs.status, fe.status):
            continue
        subject = f"document:{d.document.id}"
        s, e = _date_of(d.usable(start)), _date_of(d.usable(end))
        if not s or not e:
            out.append(Eval(subject, O.INCONCLUSIVE, f"Dates in '{d.label}' could not both be read unambiguously "
                            f"('{fs.raw_value}', '{fe.raw_value}').", f"{rule.title}: unclear dates in {d.label}",
                            "unclear_field", [d.document.id], [fs.id, fe.id], [_ev(d, fs), _ev(d, fe)]))
        elif s > e:
            out.append(Eval(subject, O.ISSUE, f"In '{d.label}' the {start} ({fs.raw_value}) is later than the "
                            f"{end} ({fe.raw_value}).", f"Issue date after validity date: {d.label}", "date_conflict",
                            [d.document.id], [fs.id, fe.id], [_ev(d, fs), _ev(d, fe)],
                            [{"source": start, "value": s}, {"source": end, "value": e}]))
        else:
            out.append(Eval(subject, O.PASS, f"Dates in '{d.label}' are in order.", rule.title, "date_conflict",
                            [d.document.id], [fs.id, fe.id]))
    return out or [Eval("application", O.NOT_APPLICABLE, f"No document states both {start} and {end}.", rule.title,
                        "date_conflict")]


def eval_expiry(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    name = p["field_name"]
    cats = set(p.get("categories") or [])
    if ctx.scrutiny_date is None:
        return [Eval("application", O.INCONCLUSIVE,
                     "The scrutiny reference date is unavailable, so stated validity dates cannot be assessed.",
                     f"{rule.title}: reference date unavailable", "expired_validity",
                     missing_evidence="A scrutiny reference date derived from the application or explicitly supplied.")]
    today = ctx.scrutiny_date.isoformat()
    out = []
    for d in ctx.originals():
        if cats and d.document.category.value not in cats:
            continue
        f = d.field(name)
        if f is None or f.status == FieldStatus.NOT_FOUND:
            continue  # never infer a validity period
        subject = f"document:{d.document.id}"
        value = _date_of(d.usable(name))
        if not value:
            out.append(Eval(subject, O.INCONCLUSIVE, f"The validity date in '{d.label}' ('{f.raw_value}') could not "
                            "be read unambiguously, so expiry was not assessed.",
                            f"{rule.title}: unclear date in {d.label}", "unclear_field", [d.document.id], [f.id],
                            [_ev(d, f)]))
        elif value < today:
            out.append(Eval(subject, O.ISSUE, f"'{d.label}' states it is valid until {f.raw_value} ({value}), which is "
                            f"before the scrutiny date {today}.", f"Stated validity date has passed: {d.label}",
                            "expired_validity", [d.document.id], [f.id], [_ev(d, f)],
                            [{"source": "stated validity", "value": value}, {"source": "scrutiny date", "value": today}]))
        else:
            out.append(Eval(subject, O.PASS, f"'{d.label}' states validity until {value}.", rule.title,
                            "expired_validity", [d.document.id], [f.id], [_ev(d, f)]))
    return out or [Eval("application", O.NOT_APPLICABLE, "No document explicitly states a validity date.", rule.title,
                        "expired_validity")]


def eval_simulated_issuer(rule: ScrutinyRule, p: dict, ctx: Ctx) -> list[Eval]:
    out = []
    for d in ctx.documents:
        attempt = ctx.verifications.get(d.document.id)
        if attempt is None:
            continue
        subject = f"document:{d.document.id}"
        label = issuer_verification.SIMULATION_LABEL
        outcome = {VerificationOutcome.SIMULATED_MATCH: O.PASS, VerificationOutcome.SIMULATED_MISMATCH: O.ISSUE,
                   VerificationOutcome.SIMULATED_EXPIRED: O.ISSUE}.get(attempt.outcome, O.INCONCLUSIVE)
        out.append(Eval(subject, outcome, f"[{label}] {attempt.outcome.value}: {attempt.explanation}",
                        f"Simulated issuer check: {attempt.outcome.value.replace('_', ' ')} ({d.label})",
                        "simulated_issuer_check", [d.document.id], evidence=[_doc_ref(d)],
                        compared_values=attempt.fields_compared))
    return out or [Eval("application", O.NOT_APPLICABLE, "No simulated issuer checks have been run.", rule.title,
                        "simulated_issuer_check")]


EVALUATORS = {
    RuleType.EXPECTED_DOCUMENT: eval_expected_document,
    RuleType.VALIDITY_PERIOD: eval_validity_period,
    RuleType.CONDITIONAL_DOCUMENT: eval_conditional_document,
    RuleType.ISSUER_AUTHORITY: eval_issuer_authority,
    RuleType.ALTERNATIVE_DOCUMENT_GROUP: eval_alternative_document_group,
    RuleType.REQUIRED_FIELD: eval_required_field,
    RuleType.PROCESSING_QUALITY: eval_processing_quality,
    RuleType.CLASSIFICATION_CONSISTENCY: eval_classification,
    RuleType.INSTITUTION_NAME_MATCH: eval_institution_name,
    RuleType.FIELD_CONSISTENCY: eval_field_consistency,
    RuleType.AREA_CONSISTENCY: eval_area,
    RuleType.DATE_ORDER: eval_date_order,
    RuleType.EXPIRY_BEFORE_SCRUTINY: eval_expiry,
    RuleType.SIMULATED_ISSUER_OUTCOME: eval_simulated_issuer,
}


# --- Anomaly indicators ----------------------------------------------------------------------------

@dataclass
class Indicator:
    detector: str
    subject: str
    title: str
    explanation: str
    uncertainty: str
    severity: Severity
    document_ids: list[str]
    evidence: list[dict] = field(default_factory=list)
    compared_values: list[dict] = field(default_factory=list)


def detect_anomalies(ctx: Ctx) -> list[Indicator]:
    out: list[Indicator] = []
    for d in ctx.documents:
        doc = d.document
        if doc.status == DocumentStatus.DUPLICATE_DETECTED and doc.duplicate_of_id:
            original = next((o for o in ctx.documents if o.document.id == doc.duplicate_of_id), None)
            out.append(Indicator(
                "exact_duplicate", doc.id, f"Exact duplicate file: {d.label}",
                f"'{d.label}' has identical content (SHA-256) to '{original.label if original else 'an earlier upload'}'.",
                "Identical files are usually accidental re-uploads. This is not evidence of misconduct.",
                Severity.LOW, [doc.id] + ([original.document.id] if original else []),
                [_doc_ref(d)] + ([_doc_ref(original)] if original else [])))
        if d.other_app_matches:
            out.append(Indicator(
                "content_in_other_application", doc.id, f"Same file content in another application: {d.label}",
                f"Identical content to '{d.label}' exists in {d.other_app_matches} other application(s). "
                "Details of other applications are not shown.",
                "May be benign (e.g. a shared trust document for institutions run by one trust). Requires review.",
                Severity.MEDIUM, [doc.id], [_doc_ref(d)]))
        proc = d.processing
        if proc and proc.status != ProcessingStatus.FAILED:
            strong = [a for a in proc.classification_alternatives if a.get("score", 0) >= 8]
            top_score = sum(s["weight"] for s in proc.classification_signals)
            if proc.predicted_category and strong and top_score >= 8:
                out.append(Indicator(
                    "mixed_document_type_signals", doc.id, f"Text signals for several document types: {d.label}",
                    f"'{d.label}' contains strong signals for {LABELS[proc.predicted_category]} and for "
                    + ", ".join(a["category"].replace("_", " ") for a in strong) + ".",
                    "Combined or multi-part documents are common; check that the file contains what its category says.",
                    Severity.LOW, [doc.id], [_doc_ref(d)]))
            eofs = (proc.pdf_properties or {}).get("eof_markers", 1)
            if eofs and eofs >= 3:
                out.append(Indicator(
                    "pdf_incremental_updates", doc.id, f"PDF saved incrementally several times: {d.label}",
                    f"The file structure shows {eofs} end-of-file markers, meaning it was modified {eofs - 1} times "
                    "after it was first written.",
                    "Very common for legitimately edited, form-filled or digitally signed PDFs. It is a structural "
                    "fact only and is not evidence of tampering. No signature validation is performed.",
                    Severity.INFO, [doc.id], [_doc_ref(d)]))

    # Same certificate number on documents of different selected categories; or with different issue dates.
    by_number: dict[str, list[tuple[DocCtx, ExtractedField]]] = {}
    for d in ctx.originals():
        f = d.usable("certificate_number")
        if f:
            by_number.setdefault(normalize_identifier(f.raw_value), []).append((d, f))
    for number, items in sorted(by_number.items()):
        if len(items) < 2:
            continue
        categories = {d.document.category for d, _ in items}
        dates = {_date_of(d.usable("issue_date")) for d, _ in items} - {None}
        if len(categories) > 1 or len(dates) > 1:
            why = []
            if len(categories) > 1:
                why.append("documents of different types")
            if len(dates) > 1:
                why.append("different issue dates")
            out.append(Indicator(
                "certificate_number_reused", f"certificate:{number}",
                f"Certificate number {items[0][1].raw_value} appears on {' and '.join(why)}",
                "The same certificate number appears in: "
                + "; ".join(f"'{d.label}' ({LABELS[d.document.category]}, p.{f.page_number})" for d, f in items) + ".",
                "Could be a typing error or a cross-reference between documents. Requires review; not a conclusion.",
                Severity.MEDIUM, [d.document.id for d, _ in items], [_ev(d, f) for d, f in items],
                [{"source": f"'{d.label}'", "value": f.raw_value,
                  "issue_date": _date_of(d.usable("issue_date"))} for d, f in items]))
    return out


# --- Runs ------------------------------------------------------------------------------------------

def _rule_snapshot(rules: list[ScrutinyRule]) -> list[dict]:
    return [{"rule_id": r.rule_id, "version": r.version, "title": r.title, "rule_type": r.rule_type.value,
             "parameters": r.parameters, "severity": r.severity.value, "source": r.source,
             "source_reference": r.source_reference,
             "source_verification_status": r.source_verification_status.value, "is_demo_only": r.is_demo_only,
             "provenance": r.provenance, "effective_from": r.effective_from, "effective_to": r.effective_to,
             "evaluator_version": EVALUATOR_VERSION}
            for r in rules]


def _needs_processing(session: Session, document: Document) -> bool:
    return not processing_service.is_current(processing_service.get_processing(session, document.id), document)


def _evaluate_rule(rule, ctx: Ctx, demo_profile: bool) -> list[Eval]:
    if demo_profile and rule.rule_id == "R01":
        return _demo_aph_fire_safety(rule, ctx)
    if demo_profile and rule.rule_id == "R02":
        return _demo_aph_alternative_group(rule, ctx)
    return EVALUATORS[rule.rule_type](rule, rule.parameters, ctx)


def start_run(session: Session, storage: DocumentStorage, settings: Settings, ocr, application_code: str,
              scrutiny_date: date | None = None, ruleset_profile: str = "production") -> ScrutinyRun:
    application = get_application(session, application_code)
    if ruleset_profile == aph_demo_ruleset.PROFILE_ID:
        if scrutiny_date is not None:
            raise AppError(
                422, "demo_ruleset_submission_date_required",
                "The APH demo profile uses only the application submission date; scrutiny_date overrides are not allowed.",
            )
        if application.institution.institution_type != InstitutionType.PRIVATE_SELF_FINANCING:
            raise AppError(
                422, "demo_ruleset_not_applicable",
                "The APH demo profile is limited to existing private self-financing technical institutions.",
            )
    if scrutiny_date is not None:
        reference_date = scrutiny_date
        reference_date_source = "operator_override"
    elif application.submitted_at is not None:
        reference_date = application.submitted_at.date()
        reference_date_source = "application_marked_ready_internal"
    else:
        reference_date = None
        reference_date_source = "unavailable"
    running = session.execute(select(ScrutinyRun).where(ScrutinyRun.application_id == application.id,
                                                        ScrutinyRun.status == RunStatus.RUNNING)).scalars().all()
    for stale in running:
        if utcnow() - stale.started_at > STALE_RUN_AFTER:
            stale.status, stale.failure_reason, stale.finished_at = RunStatus.FAILED, "Run did not finish.", utcnow()
        else:
            raise ConflictError("scrutiny_run_in_progress", "A scrutiny run is already in progress for this application.")
    number = (session.execute(select(func.max(ScrutinyRun.run_number))
                              .where(ScrutinyRun.application_id == application.id)).scalar() or 0) + 1
    run = ScrutinyRun(application_id=application.id, run_number=number, status=RunStatus.RUNNING,
                      scrutiny_date=reference_date.isoformat() if reference_date else None,
                      scrutiny_date_source=reference_date_source, rule_set_version="pending")
    session.add(run)
    session.commit()
    run_id = run.id

    try:
        _execute(session, storage, settings, ocr, run, application, reference_date, reference_date_source,
                 ruleset_profile)
    except Exception as exc:
        session.rollback()
        logger.error("Scrutiny run failed", exc_info=exc, extra={"error_type": type(exc).__name__})
        run = session.get(ScrutinyRun, run_id)
        run.status, run.finished_at = RunStatus.FAILED, utcnow()
        run.failure_reason = "The scrutiny run failed unexpectedly. Previous runs are unaffected; please retry."
        audit.record(session, "scrutiny.run_completed", "scrutiny_run", run_id, application_id=application.id,
                     outcome=AuditOutcome.FAILURE, details={"run_number": run.run_number, "status": "failed"})
        session.commit()
    return get_run(session, run_id)


def _execute(session, storage, settings, ocr, run: ScrutinyRun, application: Application, today: date | None,
             date_source: str, ruleset_profile: str = "production") -> None:
    warnings: list[str] = []
    docs = session.execute(select(Document).where(Document.application_id == application.id,
                                                  Document.status != DocumentStatus.INTAKE_FAILED)
                           .order_by(Document.uploaded_at, Document.id)).scalars().all()
    for d in docs:
        if _needs_processing(session, d):
            proc, _ = processing_service.process_document(session, storage, settings, ocr, d)
            if proc.status == ProcessingStatus.FAILED:
                warnings.append(f"'{d.original_filename}': {proc.failure_reason}")
    ocr_missing = any(p.status.value == "insufficient_text" for d in docs
                      for proc in [processing_service.get_processing(session, d.id)] if proc for p in proc.pages)
    if ocr_missing and not (ocr and ocr.available):
        warnings.append("Some pages had no text layer and OCR is not available; those pages were not read.")

    ctx = build_context(session, application, today, date_source)
    demo_profile = ruleset_profile == aph_demo_ruleset.PROFILE_ID
    if demo_profile:
        rules = list(aph_demo_ruleset.DEMO_RULES)
        snapshot = [aph_demo_ruleset.snapshot_rule(rule, EVALUATOR_VERSION) for rule in rules]
        warnings.append(aph_demo_ruleset.DEMO_NOTICE)
    else:
        rules = session.execute(select(ScrutinyRule).where(ScrutinyRule.enabled.is_(True),
                                                            ScrutinyRule.retired.is_(False))
                                .order_by(ScrutinyRule.rule_id)).scalars().all()
        snapshot = _rule_snapshot(rules)
    run.rule_snapshot = snapshot
    run.rule_set_version = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:12]
    logger.info(
        "Scrutiny ruleset selected",
        extra={"ruleset_profile": aph_demo_ruleset.PROFILE_ID if demo_profile else "production",
               "ruleset_version": aph_demo_ruleset.PROFILE_VERSION if demo_profile else run.rule_set_version,
               "rule_set_version": run.rule_set_version, "rule_count": len(rules)},
    )
    run.documents_considered = [
        {"document_id": d.document.id, "filename": d.label, "category": d.document.category.value,
         "sha256": d.document.sha256, "intake_status": d.document.status.value,
         "processing_status": d.processing.status.value if d.processing else "not_processed",
         "predicted_category": d.processing.predicted_category.value
         if d.processing and d.processing.predicted_category else None}
        for d in ctx.documents]

    position = 0
    rule_findings = 0
    outcomes = {o.value: 0 for o in O}
    severities = {s.value: 0 for s in Severity}
    for rule in rules:
        if rule.provenance in ("regulatory", "checklist") and today is not None:
            try:
                starts = date.fromisoformat(rule.effective_from) if rule.effective_from else None
                ends = date.fromisoformat(rule.effective_to) if rule.effective_to else None
            except ValueError as exc:
                raise ValueError(f"Rule {rule.rule_id} has an invalid effective date.") from exc
            if (starts is not None and today < starts) or (ends is not None and today > ends):
                evaluations = [Eval(
                    "application", O.NOT_APPLICABLE,
                    f"Reference date {today.isoformat()} is outside the rule's effective period "
                    f"({rule.effective_from or 'unknown'} to {rule.effective_to or 'unknown'}).",
                    rule.title, "rule_not_effective",
                    compared_values=[{"source": "reference_date", "value": today.isoformat(),
                                      "date_source": date_source},
                                     {"source": "effective_period", "from": rule.effective_from,
                                      "to": rule.effective_to}],
                )]
            else:
                evaluations = _evaluate_rule(rule, ctx, demo_profile)
                if starts is None or ends is None:
                    for evaluation in evaluations:
                        evaluation.explanation += " The rule's effective period is unknown."
                        evaluation.compared_values.append(
                            {"source": "effective_period", "from": rule.effective_from,
                             "to": rule.effective_to, "status": "unknown"}
                        )
        else:
            evaluations = _evaluate_rule(rule, ctx, demo_profile)
            if rule.provenance in ("regulatory", "checklist") and today is None:
                for evaluation in evaluations:
                    evaluation.explanation += " The effective period could not be checked because the reference date is unavailable."
                    evaluation.compared_values.append(
                        {"source": "effective_period", "from": rule.effective_from,
                         "to": rule.effective_to, "status": "unchecked"}
                    )
        for e in evaluations:
            if demo_profile:
                e.explanation = f"{aph_demo_ruleset.DEMO_NOTICE}. {e.explanation}"
            e.compared_values.append(
                {"source": "scrutiny_reference_date", "value": today.isoformat() if today else None,
                 "date_source": date_source}
            )
            review = e.outcome in (O.ISSUE, O.INCONCLUSIVE)
            evaluation = RuleEvaluation(
                run_id=run.id, position=position, rule_id=rule.rule_id, rule_version=rule.version,
                subject_key=e.subject_key, outcome=e.outcome, severity=rule.severity, explanation=e.explanation,
                document_ids=e.document_ids, field_ids=e.field_ids, evidence=e.evidence,
                compared_values=e.compared_values, missing_evidence=e.missing_evidence,
                human_review_recommended=review)
            position += 1
            session.add(evaluation)
            outcomes[e.outcome.value] += 1
            if review:
                session.flush()
                severity = rule.severity if e.outcome == O.ISSUE else _lower(rule.severity)
                severities[severity.value] += 1
                rule_findings += 1
                session.add(Finding(
                    application_id=application.id, run_id=run.id, evaluation_id=evaluation.id,
                    finding_key=f"rule:{rule.rule_id}:{e.subject_key}", kind=FindingKind.RULE_FINDING,
                    finding_type=e.finding_type, title=e.title[:300], severity=severity, outcome=e.outcome,
                    explanation=e.explanation, rule_id=rule.rule_id, rule_version=rule.version,
                    document_ids=e.document_ids, field_ids=e.field_ids, evidence=e.evidence,
                    compared_values=e.compared_values, missing_evidence=e.missing_evidence,
                    human_review_recommended=True))

    indicators = detect_anomalies(ctx)
    for ind in indicators:
        if demo_profile:
            ind.explanation = f"{aph_demo_ruleset.DEMO_NOTICE}. {ind.explanation}"
        severities[ind.severity.value] += 1
        session.add(Finding(
            application_id=application.id, run_id=run.id, finding_key=f"anomaly:{ind.detector}:{ind.subject}",
            kind=FindingKind.ANOMALY_INDICATOR, finding_type=ind.detector, title=ind.title[:300],
            severity=ind.severity, outcome=O.INCONCLUSIVE, explanation=ind.explanation, uncertainty=ind.uncertainty,
            detector=ind.detector, document_ids=ind.document_ids, evidence=ind.evidence,
            compared_values=ind.compared_values, human_review_recommended=True))

    run.summary = {
        "evaluation_outcomes": outcomes,
        "finding_severities": severities,
        "rule_findings": rule_findings,
        "anomaly_indicators": len(indicators),
        "documents_considered": len(ctx.documents),
        "documents_processed_ok": sum(1 for d in ctx.documents if d.processed_ok()),
        "rules_evaluated": len(rules),
    }
    run.warnings = warnings
    run.status = RunStatus.COMPLETED_WITH_WARNINGS if warnings else RunStatus.COMPLETED
    run.finished_at = utcnow()
    session.flush()
    _after_run(session, run, application)
    session.commit()


def _after_run(session: Session, run: ScrutinyRun, application: Application) -> None:
    """Carry human review state forward from the previous run, raise alerts, record the audit event."""
    from app.services import review  # local import: review depends on this module

    previous = session.execute(select(ScrutinyRun.id).where(
        ScrutinyRun.application_id == application.id, ScrutinyRun.run_number < run.run_number,
        ScrutinyRun.status != RunStatus.FAILED).order_by(ScrutinyRun.run_number.desc()).limit(1)).scalar()
    carried = review.carry_forward(session, run.id, previous, application.id)
    findings = session.execute(select(Finding).where(Finding.run_id == run.id)).scalars().all()
    issues = [f for f in findings if f.outcome == O.ISSUE and f.kind == FindingKind.RULE_FINDING]
    for f in issues:
        if f.severity == Severity.HIGH and f.review_status in (ReviewStatus.NOT_REVIEWED, ReviewStatus.CONFIRMED,
                                                               ReviewStatus.ESCALATED, ReviewStatus.AWAITING_EVIDENCE):
            alerts.raise_alert(session, dedup_key=f"high_finding:{application.id}:{f.finding_key}",
                               application_id=application.id, event_type="high_severity_finding", severity="high",
                               finding_id=f.id, title="New high-severity finding",
                               message=f"{application.application_code}: {f.title[:200]}")
    if issues:
        alerts.raise_alert(session, dedup_key=f"run_issues:{run.id}", application_id=application.id,
                           event_type="scrutiny_completed_with_issues", severity="medium",
                           title=f"Scrutiny run #{run.run_number} completed with issues",
                           message=f"{application.application_code}: {len(issues)} issue finding(s) need human review.")
    audit.record(session, "scrutiny.run_completed", "scrutiny_run", run.id, application_id=application.id,
                 details={"run_number": run.run_number, "status": run.status.value,
                          "rule_set_version": run.rule_set_version, "issues": len(issues),
                          "findings": len(findings), "carried_forward_reviews": carried})


def _lower(severity: Severity) -> Severity:
    """Inconclusive results are reported one severity step lower than a confirmed issue."""
    order = list(Severity)
    return order[max(0, order.index(severity) - 1)]


# --- Queries ---------------------------------------------------------------------------------------

def get_run(session: Session, run_id: str) -> ScrutinyRun:
    run = session.get(ScrutinyRun, run_id)
    if run is None:
        raise NotFoundError("Scrutiny run was not found.")
    return run


def list_runs(session: Session, application_code: str, page: int, page_size: int) -> tuple[list[ScrutinyRun], int]:
    application = get_application(session, application_code)
    base = select(ScrutinyRun).where(ScrutinyRun.application_id == application.id)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(base.order_by(ScrutinyRun.run_number.desc()).limit(page_size)
                           .offset((page - 1) * page_size)).scalars().all()
    return list(rows), total


def list_findings(session: Session, run: ScrutinyRun, *, page: int, page_size: int, severity=None, kind=None,
                  outcome=None, review_status=None) -> tuple[list[Finding], int]:
    stmt = select(Finding).where(Finding.run_id == run.id)
    if severity:
        stmt = stmt.where(Finding.severity == severity)
    if kind:
        stmt = stmt.where(Finding.kind == kind)
    if outcome:
        stmt = stmt.where(Finding.outcome == outcome)
    if review_status:
        stmt = stmt.where(Finding.review_status == review_status)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}
    rows = session.execute(stmt).scalars().all()
    rows = sorted(rows, key=lambda f: (f.kind != FindingKind.RULE_FINDING, f.outcome != O.ISSUE,
                                       order[f.severity], f.finding_key))
    start = (page - 1) * page_size
    return rows[start:start + page_size], total


def latest_run(session: Session, application_id: str) -> ScrutinyRun | None:
    return session.execute(select(ScrutinyRun).where(ScrutinyRun.application_id == application_id)
                           .order_by(ScrutinyRun.run_number.desc()).limit(1)).scalar_one_or_none()


def get_finding(session: Session, finding_id: str) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None:
        raise NotFoundError("Finding was not found.")
    return finding


def evaluation_rule(snapshot: list[dict], rule_id: str | None) -> dict | None:
    return next((r for r in snapshot if r["rule_id"] == rule_id), None) if rule_id else None


def ensure_application_scope(finding_or_run, application_id: str) -> None:
    if finding_or_run.application_id != application_id:
        raise NotFoundError("Not found for this application.")
