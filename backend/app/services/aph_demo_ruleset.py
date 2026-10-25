"""Explicit, demo-only mapping from drafted APH candidates to scrutiny rule IDs."""

from dataclasses import dataclass

from app.models.enums import DocumentCategory, RuleType, Severity, SourceVerificationStatus

PROFILE_ID = "aph_eoa_demo"
PROFILE_VERSION = "1"
DEMO_NOTICE = "DEMO RULESET - formal approval pending"
SOURCE_SHA256 = "153d54816f2cf11489218e239113544e8d49b73680009688baa7dc4880636051"
SOURCE_NAME = "AICTE Approval Process Handbook (local source; not independently verified)"


@dataclass(frozen=True)
class DemoRule:
    rule_id: str
    candidate_id: str
    title: str
    description: str
    rule_type: RuleType
    parameters: dict
    severity: Severity
    source: str
    source_reference: str
    source_verification_status: SourceVerificationStatus
    is_demo_only: bool
    provenance: str
    version: int
    effective_from: str | None
    effective_to: str | None
    citation: dict
    alternatives: list[dict] | None = None


def _citation(clause: str, quote: str, quote_hash: str) -> dict:
    return {
        "source_sha256": SOURCE_SHA256,
        "pdf_page_number": 97,
        "printed_page_label": "81",
        "clause_reference": clause,
        "quote": quote,
        "quote_sha256": quote_hash,
        "ocr_derived": False,
    }


_FIRE_QUOTE = "A valid Fire Safety Certificate issued by the Competent Authority."
_ALT_QUOTE = "valid Occupancy/ Completion Certificate/\nBuilding License/ Form D issued by the Competent Authority."
_STRUCTURAL_QUOTE = (
    "Valid Structural Stability Certificate from the registered Structural Engineer, if the Building is more "
    "than thirty \nyears from the issue of Completion Certificate that the Building is fit for human habitation."
)

_ALT_CITATION = _citation(
    "Annexure-2, section 2.1(iii)",
    _ALT_QUOTE,
    "fc33794c0694ae433af110faadbabf8a1a36ff28b8fc138ac5ad4f3e6128b98a",
)


DEMO_RULES = (
    DemoRule(
        rule_id="R01",
        candidate_id="APH-101",
        title="Fire safety certificate validity requires review",
        description="Checks the presence and stated validity of fire safety evidence against the packet submission date.",
        rule_type=RuleType.EXPECTED_DOCUMENT,
        parameters={"category": DocumentCategory.FIRE_SAFETY_CERTIFICATE},
        severity=Severity.MEDIUM,
        source=SOURCE_NAME,
        source_reference="Annexure-2, section 2.1(v)",
        source_verification_status=SourceVerificationStatus.UNVERIFIED,
        is_demo_only=True,
        provenance="regulatory",
        version=1,
        effective_from=None,
        effective_to=None,
        citation=_citation(
            "Annexure-2, section 2.1(v)",
            _FIRE_QUOTE,
            "0a2e48102638d542723a96d8a923df923c04588faab6d9e02904672b3841dd55",
        ),
    ),
    DemoRule(
        rule_id="R02",
        candidate_id="APH-102",
        title="One valid building-document alternative requires review",
        description="Treats Occupancy Certificate, Completion Certificate, Building License and Form D as alternatives.",
        rule_type=RuleType.ALTERNATIVE_DOCUMENT_GROUP,
        parameters={
            "categories": [
                DocumentCategory.OCCUPANCY_CERTIFICATE,
                DocumentCategory.COMPLETION_CERTIFICATE,
                DocumentCategory.BUILDING_LICENSE,
                DocumentCategory.FORM_D,
            ],
            "application_types": [
                "eoa_no_change",
                "increase_in_intake",
                "reduction_in_intake",
                "introduction_of_new_course",
                "change_of_institution_name",
            ],
            "validity_reference": "application_submission_date",
        },
        severity=Severity.MEDIUM,
        source=SOURCE_NAME,
        source_reference="Annexure-2, section 2.1(iii)",
        source_verification_status=SourceVerificationStatus.UNVERIFIED,
        is_demo_only=True,
        provenance="regulatory",
        version=1,
        effective_from=None,
        effective_to=None,
        citation=_ALT_CITATION,
        alternatives=[
            {"rule_id": "R04", "candidate_id": "APH-104", "category": "occupancy_certificate",
             "citation": _ALT_CITATION},
            {"rule_id": "R05", "candidate_id": "APH-105", "category": "completion_certificate",
             "citation": _ALT_CITATION},
            {"rule_id": "R06", "candidate_id": "APH-106", "category": "building_license",
             "citation": _ALT_CITATION},
            {"rule_id": "R07", "candidate_id": "APH-107", "category": "form_d",
             "citation": _ALT_CITATION},
        ],
    ),
    DemoRule(
        rule_id="R08",
        candidate_id="APH-108",
        title="Building age may require structural-stability evidence",
        description="Checks whether a completion certificate date is more than 30 years before application submission.",
        rule_type=RuleType.CONDITIONAL_DOCUMENT,
        parameters={
            "required_category": DocumentCategory.STRUCTURAL_STABILITY_CERTIFICATE,
            "trigger_category": DocumentCategory.COMPLETION_CERTIFICATE,
            "trigger_field": "issue_date",
            "years_elapsed": 30,
            "comparison": "strictly_more_than",
            "reference_date_source": "application_marked_ready_internal",
        },
        severity=Severity.HIGH,
        source=SOURCE_NAME,
        source_reference="Annexure-2, section 2.1(iv)",
        source_verification_status=SourceVerificationStatus.UNVERIFIED,
        is_demo_only=True,
        provenance="regulatory",
        version=1,
        effective_from=None,
        effective_to=None,
        citation=_citation(
            "Annexure-2, section 2.1(iv)",
            _STRUCTURAL_QUOTE,
            "38866bc466d2d60c1bf36f8502cddfd1eb82f188238049e46f9f5a3c11a924c4",
        ),
    ),
)


def snapshot_rule(rule: DemoRule, evaluator_version: str) -> dict:
    return {
        "rule_id": rule.rule_id,
        "version": rule.version,
        "title": rule.title,
        "rule_type": rule.rule_type.value,
        "parameters": rule.parameters,
        "severity": rule.severity.value,
        "source": rule.source,
        "source_reference": rule.source_reference,
        "source_verification_status": rule.source_verification_status.value,
        "is_demo_only": rule.is_demo_only,
        "provenance": rule.provenance,
        "effective_from": rule.effective_from,
        "effective_to": rule.effective_to,
        "evaluator_version": evaluator_version,
        "candidate_id": rule.candidate_id,
        "ruleset_profile": PROFILE_ID,
        "ruleset_version": PROFILE_VERSION,
        "demo_notice": DEMO_NOTICE,
        "citation": rule.citation,
        "alternatives": rule.alternatives,
    }
