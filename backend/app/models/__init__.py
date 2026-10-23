"""ORM models. Import each model here so Alembic autogenerate and metadata see it."""

from app.models.application import Application, ApplicationProgramme, IdSequence
from app.models.document import Document
from app.models.institution import Institution
from app.models.processing import DocumentPage, DocumentProcessing, ExtractedField
from app.models.scrutiny import (
    Finding,
    IssuerReferenceRecord,
    RuleEvaluation,
    ScrutinyRule,
    ScrutinyRun,
    VerificationAttempt,
)

__all__ = [
    "Application",
    "ApplicationProgramme",
    "Document",
    "DocumentPage",
    "DocumentProcessing",
    "ExtractedField",
    "Finding",
    "IdSequence",
    "Institution",
    "IssuerReferenceRecord",
    "RuleEvaluation",
    "ScrutinyRule",
    "ScrutinyRun",
    "VerificationAttempt",
]
