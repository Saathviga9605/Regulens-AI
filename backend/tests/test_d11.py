"""Pinned APH source: manifest integrity, rule provenance and classification, and the registry endpoint."""

import hashlib
import os
from pathlib import Path

import pytest

from tests.test_scrutiny import demo  # noqa: F401  (fixture)

from app.services import aph_demo_ruleset, regulatory_source

PINNED_SHA256 = "153d54816f2cf11489218e239113544e8d49b73680009688baa7dc4880636051"
CLASSIFICATIONS = {"SOURCE_VERIFIED", "PARTIALLY_VERIFIED", "UNRESOLVED", "DEMO_ONLY", "RETIRED", "INTEGRITY_CHECK"}


def test_manifest_pins_the_official_handbook() -> None:
    m = regulatory_source.manifest()
    assert m["sha256"] == PINNED_SHA256 and m["bytes"] == 4155819 and m["pdf_page_count"] == 231
    assert m["canonical_url"].startswith("https://cdnbbsr.s3waas.gov.in/") and m["canonical_url"].endswith(".pdf")
    assert m["verification"]["status"] == "verified"
    assert m["unresolved_references"][0]["reference"] == "Clause 7.17"
    for p in m["passages"]:
        if "quote_sha256" in p:
            assert hashlib.sha256(p["quote"].encode("utf-8")).hexdigest() == p["quote_sha256"]


def test_every_aph_rule_cites_a_manifest_passage_with_provenance() -> None:
    quotes = {p["quote"] for p in regulatory_source.manifest()["passages"]}
    assert aph_demo_ruleset.PROFILE_VERSION == "2"
    for rule in aph_demo_ruleset.DEMO_RULES:
        assert rule.citation["quote"] in quotes, rule.rule_id
        assert rule.citation["pdf_page_number"] == 97 and rule.citation["printed_page_label"] == "81"
        assert rule.citation["source_id"] == regulatory_source.manifest()["source_id"]
        # interpretation is stated, so nothing is classed as a plain restatement of the handbook
        assert rule.classification == "PARTIALLY_VERIFIED" and rule.interpretation


def test_regulatory_source_endpoint(client) -> None:
    body = client.get("/api/v1/regulatory-source").json()
    assert body["source"]["sha256"] == PINNED_SHA256
    # reports the profile a run uses when none is chosen (set to aph_eoa_demo in commit 58112ed)
    from app.api.v1.scrutiny import RunRequest
    assert body["aph_profile"]["default"] is (RunRequest.model_fields["ruleset_profile"].default == "aph_eoa_demo")
    assert {r["rule_id"] for r in body["aph_profile"]["rules"]} == {"R01", "R02", "R08"}
    assert all(r["quote"] and r["pdf_page"] == 97 for r in body["aph_profile"]["rules"])
    production = body["production_rules"]
    assert production and all(r["classification"] in CLASSIFICATIONS for r in production)
    # production rules carry no handbook citation, so none may be presented as source-verified
    assert not any(r["classification"] == "SOURCE_VERIFIED" for r in production)


@pytest.mark.skipif(not os.environ.get("APH_PDF"), reason="set APH_PDF to a local copy of the handbook")
def test_local_pdf_matches_manifest() -> None:
    report = regulatory_source.verify_pdf(Path(os.environ["APH_PDF"]))
    assert report["status"] == "verified", report


def test_different_file_is_reported_not_verified(tmp_path) -> None:
    other = tmp_path / "other.pdf"
    other.write_bytes(b"%PDF-1.4\n%%EOF")
    assert regulatory_source.verify_pdf(other)["status"] == "different_file"


def test_report_carries_aph_source_provenance(client, demo) -> None:
    import unicodedata

    import pymupdf

    code = demo["clean"]
    run = client.post(f"/api/v1/applications/{code}/scrutiny-runs", json={"ruleset_profile": aph_demo_ruleset.PROFILE_ID})
    assert run.status_code == 201, run.text
    pdf = client.get(f"/api/v1/applications/{code}/scrutiny-runs/{run.json()['id']}/report.pdf")
    assert pdf.status_code == 200
    with pymupdf.open(stream=pdf.content, filetype="pdf") as doc:
        text = unicodedata.normalize("NFKC", " ".join(page.get_text() for page in doc)).replace("\n", " ")
    assert "Approval Process Handbook 2024–25 to 2026–27" in text
    assert f"SHA-256 {PINNED_SHA256[:12]}" in text
    assert "partially verified" in text
