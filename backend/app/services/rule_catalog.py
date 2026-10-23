"""Rule definitions as structured data, with a validated parameter schema per rule type.

No rule here is a verified AICTE requirement. Expectation rules are DEMO-ONLY prototype configuration
(``source_verification_status = unverified``). Consistency/integrity rules are generic checks
(``not_applicable``: they are not regulatory requirements). An administrator may change parameters through the
API; parameters are validated against the schemas below and never executed as code.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScrutinyRule
from app.models.enums import ApplicationType, DocumentCategory, RuleType, Severity, SourceVerificationStatus
from app.services.extraction import FIELD_NAMES

FieldName = Literal[FIELD_NAMES]  # type: ignore[valid-type]

DEMO_SOURCE = "ReguLens prototype demonstration configuration"
DEMO_REFERENCE = "Not verified against the AICTE Approval Process Handbook or any official source"
INTEGRITY_SOURCE = "Generic document-consistency check (not a regulatory requirement)"


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedDocumentParams(_Params):
    category: DocumentCategory
    application_types: list[ApplicationType] | None = Field(default=None, description="None = all types")


class RequiredFieldParams(_Params):
    category: DocumentCategory
    field_name: FieldName


class ProcessingQualityParams(_Params):
    pass


class ClassificationConsistencyParams(_Params):
    min_confidence: Literal["medium", "high"] = "medium"


class _Thresholds(_Params):
    match_threshold: float = Field(default=0.9, ge=0.5, le=1.0)
    conflict_threshold: float = Field(default=0.6, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self):
        if self.conflict_threshold >= self.match_threshold:
            raise ValueError("conflict_threshold must be lower than match_threshold")
        return self


class InstitutionNameMatchParams(_Thresholds):
    field_name: Literal["institution_name", "trust_name"]
    institution_attribute: Literal["name", "trust_name"]
    categories: list[DocumentCategory] | None = None


class FieldConsistencyParams(_Thresholds):
    field_name: FieldName
    comparison: Literal["identifier", "text_similarity"]
    institution_attribute: Literal["address", "property_identifier"] | None = None
    categories: list[DocumentCategory] | None = None


class AreaConsistencyParams(_Params):
    field_name: Literal["built_up_area"] = "built_up_area"
    tolerance_percent: float = Field(default=1.0, ge=0.0, le=50.0)


class DateOrderParams(_Params):
    start_field: Literal["issue_date", "resolution_date"] = "issue_date"
    end_field: Literal["valid_until"] = "valid_until"


class ExpiryParams(_Params):
    field_name: Literal["valid_until"] = "valid_until"
    categories: list[DocumentCategory] | None = None


class SimulatedIssuerParams(_Params):
    pass


PARAM_SCHEMAS: dict[RuleType, type[_Params]] = {
    RuleType.EXPECTED_DOCUMENT: ExpectedDocumentParams,
    RuleType.REQUIRED_FIELD: RequiredFieldParams,
    RuleType.PROCESSING_QUALITY: ProcessingQualityParams,
    RuleType.CLASSIFICATION_CONSISTENCY: ClassificationConsistencyParams,
    RuleType.INSTITUTION_NAME_MATCH: InstitutionNameMatchParams,
    RuleType.FIELD_CONSISTENCY: FieldConsistencyParams,
    RuleType.AREA_CONSISTENCY: AreaConsistencyParams,
    RuleType.DATE_ORDER: DateOrderParams,
    RuleType.EXPIRY_BEFORE_SCRUTINY: ExpiryParams,
    RuleType.SIMULATED_ISSUER_OUTCOME: SimulatedIssuerParams,
}


def validate_parameters(rule_type: RuleType, parameters: dict) -> dict:
    """Validate and return canonical parameters (raises pydantic.ValidationError)."""
    return PARAM_SCHEMAS[rule_type].model_validate(parameters).model_dump(mode="json")


def _demo(rule_id, title, description, rule_type, params, severity):
    return dict(rule_id=rule_id, title=title, description=description, rule_type=rule_type, parameters=params,
                severity=severity, source=DEMO_SOURCE, source_reference=DEMO_REFERENCE,
                source_verification_status=SourceVerificationStatus.UNVERIFIED, is_demo_only=True)


def _integrity(rule_id, title, description, rule_type, params, severity):
    return dict(rule_id=rule_id, title=title, description=description, rule_type=rule_type, parameters=params,
                severity=severity, source=INTEGRITY_SOURCE, source_reference=None,
                source_verification_status=SourceVerificationStatus.NOT_APPLICABLE, is_demo_only=False)


DC, RT, SV = DocumentCategory, RuleType, Severity
DEFAULT_RULES: list[dict] = [
    _demo("EXP-001", "Fire safety certificate expected (demo)",
          "Demo expectation: an EoA application in this prototype is expected to include a fire safety certificate.",
          RT.EXPECTED_DOCUMENT, {"category": DC.FIRE_SAFETY_CERTIFICATE}, SV.HIGH),
    _demo("EXP-002", "Occupancy certificate expected (demo)",
          "Demo expectation: an occupancy certificate is expected for the institution's buildings.",
          RT.EXPECTED_DOCUMENT, {"category": DC.OCCUPANCY_CERTIFICATE}, SV.MEDIUM),
    _demo("EXP-003", "Structural stability certificate expected (demo)",
          "Demo expectation: a structural stability certificate is expected.",
          RT.EXPECTED_DOCUMENT, {"category": DC.STRUCTURAL_STABILITY_CERTIFICATE}, SV.MEDIUM),
    _demo("EXP-004", "Building plan expected for intake/course changes (demo)",
          "Demo expectation that applies only to 'increase in intake' and 'introduction of new course' "
          "applications: a building plan is expected.",
          RT.EXPECTED_DOCUMENT, {"category": DC.BUILDING_PLAN,
                                 "application_types": ["increase_in_intake", "introduction_of_new_course"]}, SV.LOW),
    _demo("FLD-001", "Fire safety certificate number present (demo)",
          "Demo expectation: a fire safety certificate states a certificate number.",
          RT.REQUIRED_FIELD, {"category": DC.FIRE_SAFETY_CERTIFICATE, "field_name": "certificate_number"}, SV.MEDIUM),
    _demo("FLD-002", "Fire safety certificate validity date stated (demo)",
          "Demo expectation: a fire safety certificate explicitly states a validity/expiry date. ReguLens never "
          "infers a validity period when none is written.",
          RT.REQUIRED_FIELD, {"category": DC.FIRE_SAFETY_CERTIFICATE, "field_name": "valid_until"}, SV.MEDIUM),
    _demo("FLD-003", "Structural stability certificate names its issuer (demo)",
          "Demo expectation: a structural stability certificate states the issuing authority or engineer.",
          RT.REQUIRED_FIELD, {"category": DC.STRUCTURAL_STABILITY_CERTIFICATE, "field_name": "issuing_authority"},
          SV.LOW),
    _demo("FLD-004", "University NOC reference present (demo)",
          "Demo expectation: a university NOC states its reference number.",
          RT.REQUIRED_FIELD, {"category": DC.UNIVERSITY_NOC, "field_name": "noc_reference"}, SV.LOW),
    _integrity("PRC-001", "Document readable",
               "Each uploaded document should yield readable text. Failed or partial extraction means the "
               "document must be reviewed manually.", RT.PROCESSING_QUALITY, {}, SV.MEDIUM),
    _integrity("CLS-001", "Selected category consistent with document text",
               "The category chosen at upload should agree with the type suggested by the document's own text.",
               RT.CLASSIFICATION_CONSISTENCY, {"min_confidence": "medium"}, SV.LOW),
    _integrity("CON-001", "Institution name consistent with application record",
               "Institution names stated in documents should match the institution record on the application.",
               RT.INSTITUTION_NAME_MATCH,
               {"field_name": "institution_name", "institution_attribute": "name",
                "match_threshold": 0.9, "conflict_threshold": 0.6}, SV.HIGH),
    _integrity("CON-002", "Trust/society name consistent with application record",
               "The trust or society named in a resolution should match the sponsoring body on record.",
               RT.INSTITUTION_NAME_MATCH,
               {"field_name": "trust_name", "institution_attribute": "trust_name",
                "match_threshold": 0.9, "conflict_threshold": 0.6}, SV.MEDIUM),
    _integrity("CON-003", "Survey numbers consistent across documents",
               "Survey numbers stated in different documents should be identical.",
               RT.FIELD_CONSISTENCY, {"field_name": "survey_number", "comparison": "identifier",
                                      "institution_attribute": "property_identifier",
                                      "match_threshold": 0.9, "conflict_threshold": 0.6}, SV.HIGH),
    _integrity("CON-004", "Addresses consistent with application record",
               "Addresses stated in documents should be similar to the institution address on record.",
               RT.FIELD_CONSISTENCY, {"field_name": "address", "comparison": "text_similarity",
                                      "institution_attribute": "address",
                                      "match_threshold": 0.8, "conflict_threshold": 0.4}, SV.MEDIUM),
    _integrity("CON-005", "Built-up area consistent across documents",
               "Built-up areas stated in different documents should agree (after unit conversion) within the "
               "configured tolerance.", RT.AREA_CONSISTENCY, {"tolerance_percent": 1.0}, SV.MEDIUM),
    _integrity("DAT-001", "Issue date not after stated validity date",
               "Within one document, the issue date should not be later than the explicitly stated validity date.",
               RT.DATE_ORDER, {}, SV.MEDIUM),
    _integrity("DAT-002", "Stated validity date not passed",
               "An explicitly stated validity date earlier than the scrutiny date is flagged. Documents without an "
               "explicit validity date are never assumed to be expired or valid.",
               RT.EXPIRY_BEFORE_SCRUTINY, {}, SV.HIGH),
    _integrity("VER-001", "Simulated issuer check outcome",
               "Reports the latest SIMULATED issuer-verification outcome per document. Simulated results are not "
               "verification with the issuing authority.", RT.SIMULATED_ISSUER_OUTCOME, {}, SV.MEDIUM),
]


def ensure_default_rules(session: Session) -> int:
    """Insert missing default rules. Existing rules (including admin edits) are never modified."""
    existing = set(session.execute(select(ScrutinyRule.rule_id)).scalars())
    added = 0
    for definition in DEFAULT_RULES:
        if definition["rule_id"] in existing:
            continue
        params = validate_parameters(definition["rule_type"], definition["parameters"])
        session.add(ScrutinyRule(**{**definition, "parameters": params}))
        added += 1
    if added:
        session.commit()
    return added
