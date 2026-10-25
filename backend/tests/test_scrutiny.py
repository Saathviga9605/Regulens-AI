"""Preliminary scrutiny: rules, runs, findings, anomaly indicators and simulated issuer verification.

Uses the synthetic demo dataset (seed + demo PDFs) in a temporary database and storage directory.
"""

import logging
from datetime import date
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.models import Application, AuditEvent, ExtractedField, ScrutinyRule, ScrutinyRun
from app.models.enums import DocumentCategory, RuleType, RunStatus, Severity, SourceVerificationStatus
from app.services import demo_documents, scrutiny
from app.services import rule_catalog
from app.services import seed as seed_service
from app.services.pdf_text import TesseractOcr
from tests.conftest import application_payload, institution_payload
from tests.test_documents import upload

SCRUTINY_DATE = "2026-10-23"


@pytest.fixture
def demo(app, client, settings) -> dict:
    """Seeded apps by role: clean, inconsistent, unreadable. OCR disabled (as on a machine without Tesseract)."""
    app.state.ocr_engine = TesseractOcr(None)
    with app.state.session_factory() as session:
        seed_service.seed(session)
        result = demo_documents.seed_demo_documents(session, app.state.document_storage, settings.max_upload_bytes)
        assert result.documents_created == 12, result.notes
        codes = {a.seed_key: a.application_code for a in session.execute(select(Application)).scalars()}
    return {"clean": codes["seed-app-01"], "conflict": codes["seed-app-06"], "unreadable": codes["seed-app-09"]}


def run(client: TestClient, code: str, scrutiny_date: str = SCRUTINY_DATE) -> dict:
    response = client.post(f"/api/v1/applications/{code}/scrutiny-runs", json={"scrutiny_date": scrutiny_date})
    assert response.status_code == 201, response.text
    return response.json()


def findings(client, code, run_id, **params) -> list[dict]:
    return client.get(f"/api/v1/applications/{code}/scrutiny-runs/{run_id}/findings",
                      params={"page_size": 100, **params}).json()["items"]


def docs_by_name(client, code) -> dict:
    return {d["original_filename"]: d for d in client.get(f"/api/v1/applications/{code}/documents").json()["items"]}


def outcomes(result: dict) -> dict:
    return {(e["rule_id"], e["subject_key"]): e["outcome"] for e in result["evaluations"]}


# --- default rules & administration ---------------------------------------------------------------

def test_default_rules_are_labelled_with_source_status(client) -> None:
    rules = {r["rule_id"]: r for r in client.get("/api/v1/scrutiny-rules").json()}
    assert len(rules) == 16
    assert "EXP-003" not in rules and "FLD-002" not in rules
    assert not any(rule_id.startswith("APH-") for rule_id in rules)
    for rule in rules.values():
        assert rule["source_verification_status"] != "verified"  # nothing claims official verification
        if rule["is_demo_only"]:
            assert rule["source_verification_status"] == "unverified"
            assert "Not verified" in rule["source_reference"]
    assert rules["EXP-001"]["is_demo_only"] and not rules["CON-003"]["is_demo_only"]


def test_regulatory_rule_types_have_strict_schemas_and_evaluators() -> None:
    cases = {
        RuleType.VALIDITY_PERIOD: {"category": "structural_stability_certificate", "years": 5},
        RuleType.CONDITIONAL_DOCUMENT: {
            "required_category": "structural_stability_certificate",
            "trigger_category": "completion_certificate",
            "years_elapsed": 30,
        },
        RuleType.ISSUER_AUTHORITY: {
            "category": "fire_safety_certificate",
            "authority_directory": {"Maharashtra": ["Example Fire Authority"]},
        },
        RuleType.ALTERNATIVE_DOCUMENT_GROUP: {
            "categories": ["occupancy_certificate", "completion_certificate", "building_license", "form_d"],
            "application_types": ["eoa_no_change"],
            "validity_reference": "operator_override",
        },
    }
    for rule_type, parameters in cases.items():
        validated = rule_catalog.validate_parameters(rule_type, parameters)
        assert all(validated[key] == value for key, value in parameters.items())
        assert callable(scrutiny.EVALUATORS[rule_type])
        with pytest.raises(ValidationError):
            rule_catalog.validate_parameters(rule_type, {**parameters, "python": "unsupported"})


def test_aph_alternative_group_requires_explicit_application_types_and_validity_date() -> None:
    params = {
        "categories": ["occupancy_certificate", "completion_certificate", "building_license", "form_d"],
        "application_types": ["eoa_no_change"],
        "validity_reference": "operator_override",
    }
    validated = rule_catalog.validate_parameters(RuleType.ALTERNATIVE_DOCUMENT_GROUP, params)
    assert validated["categories"] == params["categories"]
    assert validated["application_types"] == params["application_types"]
    with pytest.raises(ValidationError):
        rule_catalog.validate_parameters(RuleType.ALTERNATIVE_DOCUMENT_GROUP, {
            **params, "application_types": [],
        })
    with pytest.raises(ValidationError):
        rule_catalog.validate_parameters(RuleType.ALTERNATIVE_DOCUMENT_GROUP, {
            "categories": params["categories"], "validity_reference": "operator_override",
        })
    with pytest.raises(ValidationError):
        rule_catalog.validate_parameters(RuleType.ALTERNATIVE_DOCUMENT_GROUP, {
            **params, "categories": ["form_d", "form_d"],
        })


def test_aph_alternative_group_is_not_applicable_outside_configured_route() -> None:
    params = rule_catalog.validate_parameters(RuleType.ALTERNATIVE_DOCUMENT_GROUP, {
        "categories": ["occupancy_certificate", "completion_certificate"],
        "application_types": ["eoa_no_change"],
        "validity_reference": "operator_override",
    })
    rule = ScrutinyRule(
        rule_id="APH-102",
        title="APH building approval document alternative",
        description="Test-only registry evaluator behavior.",
        rule_type=RuleType.ALTERNATIVE_DOCUMENT_GROUP,
        parameters=params,
        severity=Severity.MEDIUM,
        enabled=True,
        source="test",
        source_verification_status=SourceVerificationStatus.UNVERIFIED,
        is_demo_only=True,
    )
    context = scrutiny.Ctx(
        application=SimpleNamespace(application_type=SimpleNamespace(value="increase_in_intake")),
        institution={},
        documents=[],
        scrutiny_date=None,
        scrutiny_date_source="unavailable",
        verifications={},
    )
    result = scrutiny.eval_alternative_document_group(rule, params, context)
    assert len(result) == 1
    assert result[0].outcome.value == "not_applicable"


def test_aph_alternative_group_keeps_validity_unknown_until_operator_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = rule_catalog.validate_parameters(RuleType.ALTERNATIVE_DOCUMENT_GROUP, {
        "categories": ["occupancy_certificate", "completion_certificate", "building_license", "form_d"],
        "application_types": ["eoa_no_change"],
        "validity_reference": "operator_override",
    })
    rule = ScrutinyRule(
        rule_id="APH-102",
        title="APH building approval document alternative",
        description="Test-only registry evaluator behavior.",
        rule_type=RuleType.ALTERNATIVE_DOCUMENT_GROUP,
        parameters=params,
        severity=Severity.MEDIUM,
        enabled=True,
        source="test",
        source_verification_status=SourceVerificationStatus.UNVERIFIED,
        is_demo_only=True,
    )
    documents = [
        SimpleNamespace(
            document=SimpleNamespace(id="valid-doc", category=DocumentCategory.FORM_D),
            label="valid-form-d.pdf", is_copy=False, processed_ok=lambda: True,
        ),
        SimpleNamespace(
            document=SimpleNamespace(id="expired-doc", category=DocumentCategory.BUILDING_LICENSE),
            label="expired-license.pdf", is_copy=False, processed_ok=lambda: True,
        ),
    ]

    def date_field(doc, _name):
        valid_until = date(2027, 1, 1) if doc.document.id == "valid-doc" else date(2026, 1, 1)
        raw = valid_until.isoformat()
        return SimpleNamespace(
            id=f"field-{doc.document.id}", field_name="valid_until", raw_value=raw, page_number=1,
            evidence_quote=f"Valid Until: {raw}",
        ), valid_until

    monkeypatch.setattr(scrutiny, "_date_field", date_field)
    context = scrutiny.Ctx(
        application=SimpleNamespace(application_type=SimpleNamespace(value="eoa_no_change")),
        institution={},
        documents=documents,
        scrutiny_date=date(2026, 10, 25),
        scrutiny_date_source="submitted_at",
        verifications={},
    )
    result = scrutiny.eval_alternative_document_group(rule, params, context)
    assert result[0].outcome.value == "inconclusive"

    context.scrutiny_date_source = "operator_override"
    result = scrutiny.eval_alternative_document_group(rule, params, context)
    assert result[0].outcome.value == "pass"
    assert len(result) == 1  # one valid alternative satisfies the group despite an expired extra upload


def test_aph_structural_certificate_threshold_is_strictly_more_than_thirty_years(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    params = rule_catalog.validate_parameters(RuleType.CONDITIONAL_DOCUMENT, {
        "required_category": "structural_stability_certificate",
        "trigger_category": "completion_certificate",
        "years_elapsed": 30,
        "comparison": "strictly_more_than",
        "reference_date_source": "operator_override",
    })
    rule = ScrutinyRule(
        rule_id="APH-103",
        title="Conditional structural stability certificate",
        description="Test-only APH conditional evaluator behavior.",
        rule_type=RuleType.CONDITIONAL_DOCUMENT,
        parameters=params,
        severity=Severity.MEDIUM,
        enabled=True,
        source="test",
        source_verification_status=SourceVerificationStatus.UNVERIFIED,
        is_demo_only=True,
    )
    completion = SimpleNamespace(
        document=SimpleNamespace(id="completion-doc", category=DocumentCategory.COMPLETION_CERTIFICATE),
        label="completion.pdf",
        is_copy=False,
        processed_ok=lambda: True,
    )
    issue_field = SimpleNamespace(
        id="issue-date", field_name="issue_date", raw_value="1996-10-25", page_number=1,
        evidence_quote="Date of Issue: 25 October 1996",
    )
    monkeypatch.setattr(scrutiny, "_date_field", lambda _doc, _name: (issue_field, date(1996, 10, 25)))
    context = scrutiny.Ctx(
        application=SimpleNamespace(application_type=SimpleNamespace(value="eoa_no_change")),
        institution={},
        documents=[completion],
        scrutiny_date=date(2026, 10, 25),
        scrutiny_date_source="operator_override",
        verifications={},
    )
    exact_threshold = scrutiny.eval_conditional_document(rule, params, context)
    assert exact_threshold[0].outcome.value == "not_applicable"

    context.scrutiny_date = date(2026, 10, 26)
    over_threshold = scrutiny.eval_conditional_document(rule, params, context)
    assert over_threshold[0].outcome.value == "issue"


def test_validity_period_rule_uses_explicit_issue_date_and_reference_date(client, demo) -> None:
    created = client.post("/api/v1/scrutiny-rules", json={
        "rule_id": "APH-101",
        "title": "Structural certificate duration",
        "description": "Checks an explicitly configured duration from the stated issue date.",
        "rule_type": "validity_period",
        "parameters": {"category": "structural_stability_certificate", "years": 1},
        "severity": "medium",
        "source": "Local test candidate",
    })
    assert created.status_code == 201, created.text
    result = run(client, demo["clean"], "2026-10-23")
    evaluation = next(e for e in result["evaluations"] if e["rule_id"] == "APH-101")
    assert evaluation["outcome"] == "issue"
    assert any(value.get("date_source") == "operator_override" for value in evaluation["compared_values"])


def test_conditional_and_issuer_authority_evaluators_run_conservatively(client, demo, app) -> None:
    for body in (
        {
            "rule_id": "APH-102",
            "title": "Conditional structural certificate",
            "description": "Evaluates a configured time-based document condition.",
            "rule_type": "conditional_document",
            "parameters": {
                "required_category": "structural_stability_certificate",
                "trigger_category": "completion_certificate",
                "years_elapsed": 30,
            },
            "severity": "medium",
            "source": "Local test candidate",
        },
    ):
        response = client.post("/api/v1/scrutiny-rules", json=body)
        assert response.status_code == 201, response.text
    with app.state.session_factory() as session:
        application = session.execute(
            select(Application).where(Application.application_code == demo["clean"])
        ).scalar_one()
        state = application.institution.state
    response = client.post("/api/v1/scrutiny-rules", json={
        "rule_id": "APH-103",
        "title": "Fire certificate issuer authority",
        "description": "Compares the stated issuer with configured authority data.",
        "rule_type": "issuer_authority",
        "parameters": {
            "category": "fire_safety_certificate",
            "authority_directory": {state: ["Synthetic Municipal Fire Services, Pune (Fictional)"]},
        },
        "severity": "medium",
        "source": "Local test candidate",
    })
    assert response.status_code == 201, response.text

    result = run(client, demo["unreadable"])
    conditional = next(e for e in result["evaluations"] if e["rule_id"] == "APH-102")
    assert conditional["outcome"] == "inconclusive"
    result = run(client, demo["clean"])
    issuer = next(e for e in result["evaluations"] if e["rule_id"] == "APH-103")
    assert issuer["outcome"] == "pass"


def test_registry_effective_period_outside_bounds_is_not_applicable(client, demo, app) -> None:
    with app.state.session_factory() as session:
        session.add(ScrutinyRule(
            rule_id="APH-104",
            title="Future effective rule",
            description="Test rule for effective-period gating.",
            rule_type=RuleType.VALIDITY_PERIOD,
            parameters={"category": "structural_stability_certificate", "years": 5},
            severity=Severity.MEDIUM,
            source="Test source",
            source_reference="Test clause",
            source_verification_status=SourceVerificationStatus.VERIFIED,
            is_demo_only=False,
            provenance="regulatory",
            registry_managed=True,
            effective_from="2027-01-01",
            version=1,
        ))
        session.commit()
    result = run(client, demo["clean"], "2026-10-23")
    evaluation = next(e for e in result["evaluations"] if e["rule_id"] == "APH-104")
    assert evaluation["outcome"] == "not_applicable"
    assert "outside the rule's effective period" in evaluation["explanation"]


def test_registry_managed_rule_only_allows_audited_enabled_toggle(client, app) -> None:
    with app.state.session_factory() as session:
        session.add(ScrutinyRule(
            rule_id="REG-101",
            title="Immutable registry rule",
            description="Test rule for the registry-managed API boundary.",
            rule_type=RuleType.EXPECTED_DOCUMENT,
            parameters={"category": "fire_safety_certificate"},
            severity=Severity.MEDIUM,
            source="Test registry source",
            source_reference="Test clause",
            source_verification_status=SourceVerificationStatus.VERIFIED,
            is_demo_only=False,
            provenance="regulatory",
            registry_managed=True,
            version=1,
        ))
        session.commit()

    rejected = client.patch("/api/v1/scrutiny-rules/REG-101", json={"title": "Changed title"})
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "registry_rule_immutable"
    disabled = client.patch("/api/v1/scrutiny-rules/REG-101", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["version"] == 1
    with app.state.session_factory() as session:
        events = session.execute(select(AuditEvent).where(
            AuditEvent.action == "registry_rule.enabled_changed",
            AuditEvent.resource_id == "REG-101",
        )).scalars().all()
    assert len(events) == 1


def test_unsubmitted_application_does_not_fall_back_to_system_date(client, code) -> None:
    response = client.post(f"/api/v1/applications/{code}/scrutiny-runs")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["scrutiny_date"] is None
    assert result["scrutiny_date_source"] == "unavailable"
    expiry = next(e for e in result["evaluations"] if e["rule_id"] == "DAT-002")
    assert expiry["outcome"] == "inconclusive"


def test_rule_update_versioning_and_validation(client) -> None:
    before = client.get("/api/v1/scrutiny-rules/CON-005").json()
    updated = client.patch("/api/v1/scrutiny-rules/CON-005", json={"parameters": {"tolerance_percent": 25}}).json()
    assert updated["version"] == before["version"] + 1
    assert updated["parameters"] == {"field_name": "built_up_area", "tolerance_percent": 25.0}
    same = client.patch("/api/v1/scrutiny-rules/CON-005", json={"parameters": {"tolerance_percent": 25}}).json()
    assert same["version"] == updated["version"]  # no-op edits do not bump the version
    for bad in ({"parameters": {"tolerance_percent": 500}}, {"parameters": {"python": "os.system('x')"}},
                {"severity": "catastrophic"}, {"rule_type": "expected_document"}, {"version": 99}):
        response = client.patch("/api/v1/scrutiny-rules/CON-005", json=bad)
        assert response.status_code == 422, bad
    assert client.patch("/api/v1/scrutiny-rules/NOPE-001", json={"enabled": False}).status_code == 404
    bad_threshold = client.patch("/api/v1/scrutiny-rules/CON-001",
                                 json={"parameters": {"field_name": "institution_name", "institution_attribute": "name",
                                                      "match_threshold": 0.6, "conflict_threshold": 0.8}})
    assert bad_threshold.status_code == 422


def test_create_rule(client) -> None:
    body = {"rule_id": "EXP-010", "title": "Completion certificate expected (demo)",
            "description": "Demo expectation.", "rule_type": "expected_document",
            "parameters": {"category": "completion_certificate"}, "severity": "low",
            "source": "Local demo configuration"}
    created = client.post("/api/v1/scrutiny-rules", json=body)
    assert created.status_code == 201
    assert created.json()["is_demo_only"] is True and created.json()["source_verification_status"] == "unverified"
    assert client.post("/api/v1/scrutiny-rules", json=body).status_code == 409
    bad = {**body, "rule_id": "EXP-011", "parameters": {"category": "passport"}}
    assert client.post("/api/v1/scrutiny-rules", json=bad).status_code == 422
    assert client.post("/api/v1/scrutiny-rules", json={**body, "rule_id": "lowercase"}).status_code == 422


# --- clean example ---------------------------------------------------------------------------------

def test_clean_example_has_no_fabricated_conflicts(client, demo) -> None:
    result = run(client, demo["clean"])
    assert result["status"] == "completed"
    assert result["summary"]["evaluation_outcomes"]["issue"] == 0
    assert findings(client, demo["clean"], result["id"]) == []
    got = outcomes(result)
    assert got[("CON-001", f"document:{docs_by_name(client, demo['clean'])['fire-safety-certificate.pdf']['id']}")] == "pass"
    assert got[("CON-003", "across_documents")] == "pass"
    assert got[("EXP-004", "application")] == "not_applicable"  # profile-specific rule (application type)
    assert got[("VER-001", "application")] == "not_applicable"


# --- inconsistent example --------------------------------------------------------------------------

def test_known_conflicts_are_found_with_evidence(client, demo) -> None:
    code = demo["conflict"]
    result = run(client, code)
    items = {f["finding_key"]: f for f in findings(client, code, result["id"])}
    names = docs_by_name(client, code)

    survey = items["rule:CON-003:across_documents"]
    assert survey["outcome"] == "issue" and survey["severity"] == "high"
    assert {names["fire-certificate-2023.pdf"]["id"], names["occupancy-certificate.pdf"]["id"]} <= set(survey["document_ids"])
    values = {e["value"] for e in survey["evidence"]}
    assert values == {"312", "318"}
    for evidence in survey["evidence"]:
        page = client.get(f"/api/v1/documents/{evidence['document_id']}/pages").json()["items"][evidence["page_number"] - 1]
        assert evidence["quote"] in page["text"]

    area = items["rule:CON-005:across_documents"]
    assert "86,000 sq. ft" in area["explanation"] and "9,500 sq. m" in area["explanation"]
    expired = items[f"rule:DAT-002:document:{names['fire-certificate-2023.pdf']['id']}"]
    assert {"source": "stated validity", "value": "2025-12-31"} in expired["compared_values"]
    assert {"source": "scrutiny date", "value": SCRUTINY_DATE} in expired["compared_values"]
    assert {"source": "scrutiny_reference_date", "value": SCRUTINY_DATE,
            "date_source": "operator_override"} in expired["compared_values"]
    dup = items[f"anomaly:exact_duplicate:{names['building-plan-copy.pdf']['id']}"]
    assert dup["kind"] == "anomaly_indicator" and dup["outcome"] == "inconclusive"
    assert "not evidence of misconduct" in dup["uncertainty"]
    for f in items.values():  # wording never concludes fraud or a decision
        text = (f["title"] + f["explanation"]).lower()
        assert not any(w in text for w in ("fraud", "forged", "approved", "rejected"))


def test_expiry_only_when_explicit_and_scrutiny_date_respected(client, demo) -> None:
    code = demo["conflict"]
    names = docs_by_name(client, code)
    fire = names["fire-certificate-2023.pdf"]["id"]
    early = run(client, code, "2025-06-01")
    assert outcomes(early)[("DAT-002", f"document:{fire}")] == "pass"
    late = run(client, code, "2026-10-23")
    assert outcomes(late)[("DAT-002", f"document:{fire}")] == "issue"
    # Occupancy certificate states no validity date: it is never evaluated for expiry.
    assert ("DAT-002", f"document:{names['occupancy-certificate.pdf']['id']}") not in outcomes(late)


def test_area_tolerance_is_configurable(client, demo) -> None:
    client.patch("/api/v1/scrutiny-rules/CON-005", json={"parameters": {"tolerance_percent": 25}})
    assert outcomes(run(client, demo["conflict"]))[("CON-005", "across_documents")] == "pass"


# --- unreadable / ambiguous example ----------------------------------------------------------------

def test_unreadable_and_miscategorised_documents(client, demo) -> None:
    code = demo["unreadable"]
    result = run(client, code)
    names = docs_by_name(client, code)
    got = outcomes(result)
    assert result["status"] == "completed_with_warnings"
    assert any("OCR is not available" in w for w in result["warnings"])
    scan, locked = names["scanned-fire-certificate.pdf"]["id"], names["completion-certificate-protected.pdf"]["id"]
    assert got[("PRC-001", f"document:{scan}")] == "issue"
    assert got[("PRC-001", f"document:{locked}")] == "issue"
    assert got[("FLD-001", f"document:{scan}")] == "inconclusive"  # unreadable is not the same as missing
    assert got[("CLS-001", f"document:{names['university-noc.pdf']['id']}")] == "issue"
    processed = client.get(f"/api/v1/documents/{names['university-noc-2026.pdf']['id']}/processing").json()
    issue_date = next(f for f in processed["fields"] if f["field_name"] == "issue_date")
    assert issue_date["status"] == "ambiguous" and issue_date["raw_value"] == "05/06/2026"


def test_ambiguous_or_ungrounded_values_are_inconclusive_not_conflicts(client, demo, app) -> None:
    code = demo["conflict"]
    run(client, code)  # processes documents
    names = docs_by_name(client, code)
    with app.state.session_factory() as s:
        field = s.execute(select(ExtractedField).where(
            ExtractedField.document_id == names["occupancy-certificate.pdf"]["id"],
            ExtractedField.field_name == "survey_number")).scalar_one()
        field.evidence_quote = "Survey No.: 999"  # tampered: not in the page text
        s.commit()
    got = outcomes(run(client, code))
    assert got[("CON-003", "across_documents")] == "pass"  # the remaining usable values agree (312, 312)
    assert got[("CON-003", "unclear_values")] == "inconclusive"


# --- runs, history, determinism, scoping ----------------------------------------------------------

def test_reruns_keep_history_and_are_deterministic(client, demo) -> None:
    code = demo["conflict"]
    first, second = run(client, code), run(client, code)
    assert (first["run_number"], second["run_number"]) == (1, 2)
    assert outcomes(first) == outcomes(second)
    assert first["rule_set_version"] == second["rule_set_version"]
    keys1 = sorted(f["finding_key"] for f in findings(client, code, first["id"]))
    keys2 = sorted(f["finding_key"] for f in findings(client, code, second["id"]))
    assert keys1 == keys2 and len(keys1) == len(set(keys1))  # stable keys, no duplicates within a run
    listing = client.get(f"/api/v1/applications/{code}/scrutiny-runs").json()
    assert [r["run_number"] for r in listing["items"]] == [2, 1]
    assert client.get(f"/api/v1/applications/{code}/scrutiny-runs/{first['id']}").json()["evaluations"]
    latest = client.get(f"/api/v1/applications/{code}/findings", params={"page_size": 100}).json()["items"]
    assert {f["run_id"] for f in latest} == {second["id"]}


def test_disabling_a_rule_changes_new_runs_only(client, demo) -> None:
    code = demo["conflict"]
    before = run(client, code)
    client.patch("/api/v1/scrutiny-rules/CON-003", json={"enabled": False})
    after = run(client, code)
    assert any(e["rule_id"] == "CON-003" for e in before["evaluations"])
    assert not any(e["rule_id"] == "CON-003" for e in after["evaluations"])
    assert before["rule_set_version"] != after["rule_set_version"]
    old = client.get(f"/api/v1/applications/{code}/scrutiny-runs/{before['id']}").json()
    assert any(r["rule_id"] == "CON-003" for r in old["rule_snapshot"])


def test_records_are_scoped_to_their_application(client, demo) -> None:
    result = run(client, demo["conflict"])
    finding = findings(client, demo["conflict"], result["id"])[0]
    other = demo["clean"]
    assert client.get(f"/api/v1/applications/{other}/scrutiny-runs/{result['id']}").status_code == 404
    assert client.get(f"/api/v1/applications/{other}/scrutiny-runs/{result['id']}/findings").status_code == 404
    assert client.get(f"/api/v1/applications/{other}/findings/{finding['id']}").status_code == 404
    assert client.patch(f"/api/v1/applications/{other}/findings/{finding['id']}/review",
                        json={"review_status": "dismissed"}).status_code == 404


def test_finding_detail_and_human_review(client, demo) -> None:
    code = demo["conflict"]
    result = run(client, code)
    finding = next(f for f in findings(client, code, result["id"]) if f["rule_id"] == "CON-003")
    detail = client.get(f"/api/v1/applications/{code}/findings/{finding['id']}").json()
    assert detail["rule"]["provenance"] == "integrity"
    assert detail["rule"]["source_verification_status"] == "not_applicable"
    assert detail["run_number"] == 1 and detail["review_status"] == "not_reviewed"
    assert "confirm" in detail["allowed_actions"] and "resolve" not in detail["allowed_actions"]
    action = client.post(f"/api/v1/applications/{code}/findings/{finding['id']}/actions",
                         json={"action": "escalate", "expected_version": detail["review_version"],
                               "note": "Ask the institution for the certificate."})
    assert action.status_code == 201, action.text
    reviewed = client.get(f"/api/v1/applications/{code}/findings/{finding['id']}").json()
    assert reviewed["review_status"] == "escalated" and reviewed["reviewed_at"]
    assert reviewed["outcome"] == "issue"  # the system result itself is unchanged by human review
    filtered = findings(client, code, result["id"], review_status="escalated")
    assert [f["id"] for f in filtered] == [finding["id"]]


def test_finding_filters_and_validation(client, demo) -> None:
    code = demo["conflict"]
    result = run(client, code)
    assert all(f["severity"] == "high" for f in findings(client, code, result["id"], severity="high"))
    assert all(f["kind"] == "anomaly_indicator" for f in findings(client, code, result["id"], kind="anomaly_indicator"))
    for params in ({"severity": "extreme"}, {"kind": "verdict"}, {"page_size": 1000}):
        assert client.get(f"/api/v1/applications/{code}/scrutiny-runs/{result['id']}/findings",
                          params=params).status_code == 422
    assert client.post(f"/api/v1/applications/{code}/scrutiny-runs",
                       json={"scrutiny_date": "1800-01-01"}).status_code == 422
    assert client.post(f"/api/v1/applications/{code}/scrutiny-runs", json={"extra": 1}).status_code == 422
    assert client.post("/api/v1/applications/REG-EoA-2026-9999/scrutiny-runs").status_code == 404
    assert client.get(f"/api/v1/applications/{code}/scrutiny-runs/nope").status_code == 404


def test_concurrent_run_is_rejected_and_failures_are_recorded(client, demo, app, monkeypatch) -> None:
    code = demo["clean"]
    with app.state.session_factory() as s:
        application = s.execute(select(Application).where(Application.application_code == code)).scalar_one()
        s.add(ScrutinyRun(application_id=application.id, run_number=1, status=RunStatus.RUNNING,
                          scrutiny_date=SCRUTINY_DATE, rule_set_version="x"))
        s.commit()
    blocked = client.post(f"/api/v1/applications/{code}/scrutiny-runs")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "scrutiny_run_in_progress"
    with app.state.session_factory() as s:
        s.execute(select(ScrutinyRun)).scalar_one().status = RunStatus.COMPLETED
        s.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated engine failure at C:\\secret\\path")

    monkeypatch.setattr(scrutiny, "detect_anomalies", boom)
    failed = run(client, code)
    assert failed["status"] == "failed" and "secret" not in failed["failure_reason"]
    assert failed["evaluations"] == []
    assert client.get(f"/api/v1/applications/{code}/scrutiny-runs").json()["total"] == 2


def test_findings_survive_document_deletion(client, demo) -> None:
    code = demo["conflict"]
    result = run(client, code)
    copy_id = docs_by_name(client, code)["building-plan-copy.pdf"]["id"]
    assert client.delete(f"/api/v1/documents/{copy_id}").status_code == 204
    kept = findings(client, code, result["id"], kind="anomaly_indicator")
    assert any(f["finding_key"] == f"anomaly:exact_duplicate:{copy_id}" for f in kept)
    rerun = findings(client, code, run(client, code)["id"], kind="anomaly_indicator")
    assert not any("exact_duplicate" in f["finding_key"] for f in rerun)


def test_certificate_number_reuse_indicator(client, code) -> None:
    lines_fire = demo_documents.FIRE_A
    lines_occ = [line.replace("SYN-OC/PUN/2024/0077", "SYN-FSC/PUN/2026/0142") for line in demo_documents.OCC_A]
    upload(client, code, demo_documents.build_pdf(lines_fire, title="a"), name="fire.pdf")
    upload(client, code, demo_documents.build_pdf(lines_occ, title="b"), name="occ.pdf",
           category="occupancy_certificate")
    result = run(client, code)
    indicator = next(f for f in findings(client, code, result["id"], kind="anomaly_indicator")
                     if f["detector"] == "certificate_number_reused")
    assert "different types" in indicator["title"] and "not a conclusion" in indicator["uncertainty"]


# --- simulated issuer verification ----------------------------------------------------------------

def verify(client, doc_id):
    return client.post(f"/api/v1/documents/{doc_id}/issuer-verifications")


def test_simulated_issuer_outcomes_are_labelled(client, demo) -> None:
    clean, conflict = docs_by_name(client, demo["clean"]), docs_by_name(client, demo["conflict"])
    for d in list(clean.values()) + list(conflict.values()):
        client.post(f"/api/v1/documents/{d['id']}/processing")
    expected = {
        clean["fire-safety-certificate.pdf"]["id"]: "simulated_match",
        clean["occupancy-certificate.pdf"]["id"]: "simulated_unavailable",
        clean["structural-stability-certificate.pdf"]["id"]: "manual_review",  # no reference configured
        clean["trust-resolution.pdf"]["id"]: "unsupported",
        conflict["fire-certificate-2023.pdf"]["id"]: "simulated_expired",
        conflict["occupancy-certificate.pdf"]["id"]: "simulated_mismatch",
    }
    for doc_id, outcome in expected.items():
        body = verify(client, doc_id).json()
        assert body["outcome"] == outcome, (doc_id, body)
        assert body["simulated"] is True
        assert body["simulation_label"] == "SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY"
        assert body["adapter"] == "mock_synthetic_registry"
    mismatch = client.get(f"/api/v1/documents/{conflict['occupancy-certificate.pdf']['id']}/issuer-verifications").json()
    assert "Riverbank" not in str(mismatch)  # reference values of the synthetic record are never exposed
    assert {"field": "institution_name", "document_value": "Hooghly Riverside Engineering College",
            "result": "mismatch"} in mismatch[0]["fields_compared"]
    history = client.get(f"/api/v1/applications/{demo['clean']}/issuer-verifications").json()
    assert history["total"] == 4

    got = outcomes(run(client, demo["conflict"]))
    assert got[("VER-001", f"document:{conflict['occupancy-certificate.pdf']['id']}")] == "issue"
    result = run(client, demo["clean"])
    assert outcomes(result)[("VER-001", f"document:{clean['fire-safety-certificate.pdf']['id']}")] == "pass"
    ver = next(e for e in result["evaluations"] if e["rule_id"] == "VER-001")
    assert ver["explanation"].startswith("[SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY]")


def test_no_match_is_manufactured_without_reference(client, code) -> None:
    doc = upload(client, code, demo_documents.build_pdf(demo_documents.FIRE_A, title="x")).json()
    assert verify(client, doc["id"]).status_code == 409  # must be processed first
    client.post(f"/api/v1/documents/{doc['id']}/processing")
    body = verify(client, doc["id"]).json()  # same numbers as a seeded record, but no reference seeded here
    assert body["outcome"] == "manual_review" and body["reference_code"] is None
    assert verify(client, "missing").status_code == 404


# --- seed ------------------------------------------------------------------------------------------

def test_demo_seed_is_idempotent_and_preserves_user_documents(client, demo, app, settings) -> None:
    user_doc = upload(client, demo["clean"], name="user-upload.pdf").json()
    with app.state.session_factory() as s:
        again = demo_documents.seed_demo_documents(s, app.state.document_storage, settings.max_upload_bytes)
        assert (again.documents_created, again.documents_skipped, again.references_created) == (0, 12, 0)
        summary = seed_service.summary(s)
    assert summary["documents_total"] == 13 and summary["documents_seeded"] == 12
    assert client.get(f"/api/v1/documents/{user_doc['id']}").json() == user_doc


def test_demo_pdfs_are_marked_fictional() -> None:
    import pymupdf

    pdf = pymupdf.open(stream=demo_documents.build_pdf(demo_documents.FIRE_A, title="x"), filetype="pdf")
    assert demo_documents.BANNER in pdf[0].get_text()
    assert pdf.metadata["title"].startswith("Fictional demo")


def test_reset_clears_scrutiny_data(client, demo, app, settings) -> None:
    run(client, demo["conflict"])
    with app.state.session_factory() as s:
        removed = seed_service.reset_data(s, settings, confirm=True)
        assert removed == 12
        assert seed_service.summary(s)["scrutiny_runs"] == 0
    rules = client.get("/api/v1/scrutiny-rules").json()
    assert len(rules) == 16  # active rules are configuration, kept
    assert not any(rule["rule_id"] in {"EXP-003", "FLD-002"} for rule in rules)


def test_scrutiny_on_application_without_documents(client, institution) -> None:
    code = client.post("/api/v1/applications", json=application_payload(institution["institution_code"])).json()[
        "application_code"]
    result = run(client, code)
    assert result["status"] == "completed"
    got = outcomes(result)
    assert got[("EXP-001", "application")] == "issue"
    assert got[("PRC-001", "application")] == "not_applicable"
    assert date.fromisoformat(result["scrutiny_date"])


def test_aph_demo_profile_isolated_cited_and_disclaimed(client, demo, caplog) -> None:
    import json

    from app.core.logging import JsonFormatter
    from app.services.aph_demo_ruleset import DEMO_NOTICE, PROFILE_ID, PROFILE_VERSION

    caplog.set_level(logging.INFO, logger="regulens.scrutiny")
    codes = {"A": demo["clean"], "B": demo["conflict"], "C": demo["unreadable"]}
    expected_r02 = {"A": "inconclusive", "B": "inconclusive", "C": "inconclusive"}
    for packet, code in codes.items():
        response = client.post(f"/api/v1/applications/{code}/scrutiny-runs",
                               json={"ruleset_profile": PROFILE_ID})
        assert response.status_code == 201, response.text
        run_result = response.json()
        assert run_result["ruleset_profile"] == PROFILE_ID
        assert run_result["ruleset_profile_version"] == PROFILE_VERSION
        assert run_result["scrutiny_date"] is None  # the demo seed has no submitted_at date
        assert DEMO_NOTICE in run_result["warnings"]

        snapshot = {item["rule_id"]: item for item in run_result["rule_snapshot"]}
        assert set(snapshot) == {"R01", "R02", "R08"}
        assert snapshot["R02"]["alternatives"] and {
            alternative["rule_id"] for alternative in snapshot["R02"]["alternatives"]
        } == {"R04", "R05", "R06", "R07"}
        assert "R03" not in snapshot  # other structural checks are deliberately skipped
        for rule in snapshot.values():
            assert rule["is_demo_only"] is True
            assert rule["source_verification_status"] == "unverified"
            assert rule["citation"]["pdf_page_number"] == 97

        findings_for_run = findings(client, code, run_result["id"])
        assert findings_for_run
        assert all(item["explanation"].startswith(DEMO_NOTICE) for item in findings_for_run)
        by_rule = {item["rule_id"]: item for item in findings_for_run if item["rule_id"]}
        assert by_rule["R01"]["outcome"] == "inconclusive"
        assert by_rule["R02"]["outcome"] == expected_r02[packet]
        assert by_rule["R08"]["outcome"] == "inconclusive"

        detail = client.get(
            f"/api/v1/applications/{code}/findings/{by_rule['R02']['id']}"
        ).json()
        assert detail["rule"]["citation"]["clause_reference"] == "Annexure-2, section 2.1(iii)"
        assert "Form D" in detail["rule"]["citation"]["quote"]

        report_response = client.get(
            f"/api/v1/applications/{code}/scrutiny-runs/{run_result['id']}/report.pdf"
        )
        assert report_response.status_code == 200
        pdf = pymupdf.open(stream=report_response.content, filetype="pdf")
        report_text = " ".join(page.get_text() for page in pdf)
        assert DEMO_NOTICE in report_text
        assert "Annexure-2, section 2.1(iii)" in report_text

    selected = [record for record in caplog.records if record.getMessage() == "Scrutiny ruleset selected"]
    demo_log = next(record for record in selected
                    if getattr(record, "ruleset_profile", None) == PROFILE_ID)
    formatted_log = json.loads(JsonFormatter().format(demo_log))
    assert formatted_log["ruleset_profile"] == PROFILE_ID
    assert formatted_log["ruleset_version"] == PROFILE_VERSION
    assert formatted_log["rule_set_version"]

    production = run(client, demo["clean"])
    assert production["ruleset_profile"] == "production"
    assert production["ruleset_profile_version"] == "database"
    assert not any(item["rule_id"].startswith("R") for item in production["rule_snapshot"])


def test_aph_demo_profile_rejects_operator_dates_and_out_of_scope_institutions(client, institution) -> None:
    code = client.post(
        "/api/v1/applications",
        json=application_payload(institution["institution_code"]),
    ).json()["application_code"]
    override = client.post(
        f"/api/v1/applications/{code}/scrutiny-runs",
        json={"ruleset_profile": "aph_eoa_demo", "scrutiny_date": SCRUTINY_DATE},
    )
    assert override.status_code == 422
    assert override.json()["error"]["code"] == "demo_ruleset_submission_date_required"

    public_institution = client.post(
        "/api/v1/institutions",
        json=institution_payload(institution_type="government", name="Synthetic Public Technical Institute"),
    ).json()
    public_code = client.post(
        "/api/v1/applications",
        json=application_payload(public_institution["institution_code"]),
    ).json()["application_code"]
    out_of_scope = client.post(
        f"/api/v1/applications/{public_code}/scrutiny-runs",
        json={"ruleset_profile": "aph_eoa_demo"},
    )
    assert out_of_scope.status_code == 422
    assert out_of_scope.json()["error"]["code"] == "demo_ruleset_not_applicable"
