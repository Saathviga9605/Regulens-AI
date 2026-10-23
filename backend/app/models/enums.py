"""Enumerations shared by models, schemas and services.

Values are stored as strings; changing a value requires a data migration.
"""

from enum import StrEnum


class InstitutionType(StrEnum):
    GOVERNMENT = "government"
    GOVERNMENT_AIDED = "government_aided"
    PRIVATE_SELF_FINANCING = "private_self_financing"
    DEEMED_UNIVERSITY = "deemed_university"
    STATE_PRIVATE_UNIVERSITY = "state_private_university"


class RecordStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ApplicationCategory(StrEnum):
    EXTENSION_OF_APPROVAL = "extension_of_approval"


class ApplicationType(StrEnum):
    EOA_NO_CHANGE = "eoa_no_change"
    INCREASE_IN_INTAKE = "increase_in_intake"
    REDUCTION_IN_INTAKE = "reduction_in_intake"
    INTRODUCTION_OF_NEW_COURSE = "introduction_of_new_course"
    CHANGE_OF_INSTITUTION_NAME = "change_of_institution_name"


class ProgrammeLevel(StrEnum):
    DIPLOMA = "diploma"
    UNDERGRADUATE = "undergraduate"
    POSTGRADUATE = "postgraduate"


class Shift(StrEnum):
    FIRST = "first"
    SECOND = "second"


class DocumentCategory(StrEnum):
    """Prototype categories. Offering a category does not mean it is mandatory for every application."""

    FIRE_SAFETY_CERTIFICATE = "fire_safety_certificate"
    OCCUPANCY_CERTIFICATE = "occupancy_certificate"
    COMPLETION_CERTIFICATE = "completion_certificate"
    STRUCTURAL_STABILITY_CERTIFICATE = "structural_stability_certificate"
    BUILDING_PLAN = "building_plan"
    UNIVERSITY_NOC = "university_noc"
    TRUST_RESOLUTION = "trust_resolution"
    OTHER = "other"


class DocumentStatus(StrEnum):
    """Intake status only. Processing and scrutiny results are stored separately."""

    UPLOADED = "uploaded"
    DUPLICATE_DETECTED = "duplicate_detected"
    INTAKE_FAILED = "intake_failed"


class ApplicationStatus(StrEnum):
    """Internal ReguLens workflow statuses. None of these is an AICTE decision."""

    DRAFT = "draft"
    READY_FOR_PRELIMINARY_SCRUTINY = "ready_for_preliminary_scrutiny"
    UNDER_PRELIMINARY_SCRUTINY = "under_preliminary_scrutiny"
    AWAITING_ADDITIONAL_EVIDENCE = "awaiting_additional_evidence"
    PRELIMINARY_SCRUTINY_COMPLETED = "preliminary_scrutiny_completed"


# --- Document processing (Deliverable 4) ------------------------------------------------------


class ProcessingStatus(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"  # e.g. some pages unreadable / OCR unavailable
    FAILED = "failed"  # corrupt, encrypted, empty or unavailable content


class PageExtractionMethod(StrEnum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    NONE = "none"


class PageStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_TEXT = "insufficient_text"  # below the threshold and OCR not attempted/available
    OCR_FAILED = "ocr_failed"
    OCR_LOW_TEXT = "ocr_low_text"  # OCR ran but still produced little text


class FieldStatus(StrEnum):
    EXTRACTED = "extracted"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    UNVERIFIED = "unverified"  # evidence quote could not be grounded in the page text


class Confidence(StrEnum):
    """Qualitative heuristic confidence; not a calibrated probability."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- Preliminary scrutiny ---------------------------------------------------------------------


class RuleType(StrEnum):
    EXPECTED_DOCUMENT = "expected_document"
    REQUIRED_FIELD = "required_field"
    PROCESSING_QUALITY = "processing_quality"
    CLASSIFICATION_CONSISTENCY = "classification_consistency"
    INSTITUTION_NAME_MATCH = "institution_name_match"
    FIELD_CONSISTENCY = "field_consistency"
    AREA_CONSISTENCY = "area_consistency"
    DATE_ORDER = "date_order"
    EXPIRY_BEFORE_SCRUTINY = "expiry_before_scrutiny"
    SIMULATED_ISSUER_OUTCOME = "simulated_issuer_outcome"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceVerificationStatus(StrEnum):
    VERIFIED = "verified"  # source text checked by a person against the cited official document
    UNVERIFIED = "unverified"  # not checked against an official source; must be shown as such
    NOT_APPLICABLE = "not_applicable"  # generic integrity/consistency check, not a regulatory requirement


class RuleOutcome(StrEnum):
    PASS = "pass"
    ISSUE = "issue"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class FindingKind(StrEnum):
    RULE_FINDING = "rule_finding"
    ANOMALY_INDICATOR = "anomaly_indicator"  # a prompt for attention, never a conclusion


class ReviewStatus(StrEnum):
    """Human-review state of a finding, changed only through review actions. Never an AICTE decision;
    'confirmed' means a reviewer agrees the finding needs attention, not that fraud or non-compliance is proven."""

    NOT_REVIEWED = "not_reviewed"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"
    AWAITING_EVIDENCE = "awaiting_evidence"
    RESOLVED = "resolved"


class ReviewActionType(StrEnum):
    CONFIRM = "confirm"
    DISMISS = "dismiss"
    ESCALATE = "escalate"
    REQUEST_EVIDENCE = "request_evidence"
    RESOLVE = "resolve"
    REOPEN = "reopen"
    NOTE = "note"
    CARRIED_FORWARD = "carried_forward"  # system: review state copied to the same finding in a newer run


class UserRole(StrEnum):
    REVIEWER = "reviewer"
    ADMIN = "admin"


class EvidenceRequestStatus(StrEnum):
    OPEN = "open"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class VerificationOutcome(StrEnum):
    """Outcomes of the SIMULATED issuer adapter. None means verification with a real authority."""

    SIMULATED_MATCH = "simulated_match"
    SIMULATED_MISMATCH = "simulated_mismatch"
    SIMULATED_EXPIRED = "simulated_expired"
    SIMULATED_UNAVAILABLE = "simulated_unavailable"
    MANUAL_REVIEW = "manual_review"
    UNSUPPORTED = "unsupported"


class ReferenceAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
