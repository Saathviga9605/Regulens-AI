"""Deliverable 9: source-verification statuses, alteration analysis, campus experiment, capture manifests, isolation."""

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text

from app.models.enums import IssuerSourceStatus as S, SourceType, SourceVerificationStatus, VerificationOutcome as V
from app.services import physical_capture, reuse_engine as engine, source_status
from app.services.image_reuse import INCONCLUSIVE, NOT_INDICATED, POTENTIAL, campus_dataset, compare_images, evaluate_campus
from app.services.reuse_dataset import build_dataset
from app.services.reuse_eval import fixture_input


# --- source-verification status ------------------------------------------------------------------

def test_every_adapter_outcome_maps_to_exactly_one_bible_label():
    expected = {V.SIMULATED_MATCH: ("Verified", SourceType.SIMULATED),
                V.SIMULATED_MISMATCH: ("Mismatch detected", SourceType.SIMULATED),
                V.SIMULATED_EXPIRED: ("Expired", SourceType.SIMULATED),
                V.SIMULATED_UNAVAILABLE: ("Source unavailable", SourceType.SIMULATED),
                V.MANUAL_REVIEW: ("Manual review required", SourceType.SIMULATED),
                V.UNSUPPORTED: ("Manual review required", SourceType.NOT_CONNECTED)}
    for outcome, (label, stype) in expected.items():
        status, got_type = source_status.map_outcome(outcome, simulated=True)
        assert (source_status.LABELS[status], got_type) == (label, stype)
    assert source_status.pending(True) == (S.VERIFICATION_PENDING, SourceType.SIMULATED)
    assert source_status.pending(False) == (S.VERIFICATION_PENDING, SourceType.NOT_CONNECTED)
    assert set(source_status.LABELS.values()) == {"Verified", "Mismatch detected", "Expired", "Verification pending",
                                                  "Source unavailable", "Manual review required"}
    assert source_status.display(S.VERIFIED, SourceType.SIMULATED) == "Verified (SIMULATED)"


def test_source_status_is_a_separate_dimension():
    # Rule-provenance enum, reuse outcomes, review dispositions and source status are distinct types/values.
    assert {s.value for s in SourceVerificationStatus} == {"verified", "unverified", "not_applicable"}
    assert set(engine.OUTCOMES).isdisjoint(set(source_status.LABELS.values()))
    from app.models.enums import PairReviewStatus, ReviewStatus
    assert not ({s.value for s in S} & ({s.value for s in PairReviewStatus} | {s.value for s in ReviewStatus}))
    assert all(source_status.map_outcome(o, True)[1] != SourceType.LIVE for o in V)  # never claims a live check


def test_simulated_check_api_reports_status_and_source_type(client):
    from app.services import demo_documents, seed
    from app.services.storage import DocumentStorage

    with client.app.state.session_factory() as session:
        seed.seed(session)
        demo_documents.seed_demo_documents(session, client.app.state.document_storage, 25_000_000)
        from app.models import Document
        doc = session.execute(select(Document).where(Document.seed_key.is_not(None))
                              .order_by(Document.seed_key)).scalars().first()
        doc_id = doc.id
    assert client.post(f"/api/v1/documents/{doc_id}/processing").status_code in (200, 201)
    r = client.post(f"/api/v1/documents/{doc_id}/issuer-verifications")
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["simulated"] is True and body["source_type"] in ("SIMULATED", "NOT_CONNECTED")
    assert body["source_status_label"] in source_status.LABELS.values()
    assert body["simulation_label"].startswith("SIMULATED")


def test_migration_0009_backfills_existing_attempts(tmp_path):
    from alembic import command

    from app.db.init_db import alembic_config, run_migrations

    db = tmp_path / "m.db"
    eng = create_engine(f"sqlite:///{db.as_posix()}")
    run_migrations(eng, "0008")
    with eng.begin() as c:
        c.execute(text("INSERT INTO institutions (id, institution_code, name, name_normalized, institution_type, state, "
                       "district, address, trust_name, property_identifier, status, created_at, updated_at) VALUES "
                       "('i1','INST-1','X','x','private_self_financing','S','D','A','T','P','active','2026-01-01','2026-01-01')"))
        c.execute(text("INSERT INTO applications (id, application_code, institution_id, category, academic_year, "
                       "application_type, status, status_changed_at, created_at, updated_at) VALUES "
                       "('a1','APP-1','i1','extension_of_approval','2026-27','eoa_no_change','draft','2026-01-01',"
                       "'2026-01-01','2026-01-01')"))
        for i, outcome in enumerate(["simulated_match", "simulated_mismatch", "simulated_expired",
                                     "simulated_unavailable", "manual_review", "unsupported"]):
            c.execute(text("INSERT INTO verification_attempts (id, application_id, document_filename, adapter, method, "
                           "simulated, outcome, explanation, fields_compared, created_at) VALUES "
                           f"('v{i}','a1','f.pdf','mock','m',1,'{outcome}','e','[]','2026-01-01')"))
    run_migrations(eng, "head")
    with sqlite3.connect(db) as conn:
        rows = dict((r[0], (r[1], r[2])) for r in conn.execute(
            "SELECT outcome, source_status, source_type FROM verification_attempts"))
    assert rows == {"simulated_match": ("verified", "SIMULATED"), "simulated_mismatch": ("mismatch_detected", "SIMULATED"),
                    "simulated_expired": ("expired", "SIMULATED"), "simulated_unavailable": ("source_unavailable", "SIMULATED"),
                    "manual_review": ("manual_review_required", "SIMULATED"),
                    "unsupported": ("manual_review_required", "NOT_CONNECTED")}
    cfg = alembic_config()
    with eng.begin() as c:
        cfg.attributes["connection"] = c
        command.downgrade(cfg, "0008")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM verification_attempts").fetchone() == (6,)
    run_migrations(eng, "head")
    eng.dispose()


# --- alteration analysis: five controlled case types ---------------------------------------------

@pytest.fixture(scope="module")
def ds():
    return build_dataset()


@pytest.mark.parametrize("split", ["dev_alt", "heldout_alt"])
def test_alteration_suite_outcomes(ds, split):
    inp = lambda k: fixture_input(ds.docs[f"{split}_{k}"], None)  # noqa: E731
    src = inp("src")
    benign = engine.compare(src, inp("vec"))
    assert benign.outcome == engine.MATCH_CONFIRMED
    one = engine.compare(src, inp("alt1"))
    assert one.outcome == engine.CANDIDATE and one.fields["conflict"] == 1
    for key in ("alt2", "alt3"):
        r = engine.compare(src, inp(key))
        assert r.outcome == engine.CANDIDATE, key  # v4: localized differences on fields → review, never confirmed
        assert r.fields["conflict"] >= 2 and r.fusion["regions"]["regions_elsewhere"] == 0
        assert "not a finding of fraud" in r.fusion["rule"]
        assert any(s["kind"] == "contradicts" for s in r.explanation["statements"])
    tmpl = engine.compare(src, inp("tmpl"))
    assert tmpl.outcome == engine.NOT_MATCHED and tmpl.fields["agree"] == 0
    poor = engine.compare(src, inp("poor"))
    assert poor.outcome in (engine.INCONCLUSIVE, engine.CANDIDATE) and poor.outcome != engine.MATCH_CONFIRMED


def test_v3_behaviour_is_reproducible_with_the_flag_off(ds):
    import dataclasses

    v3 = dataclasses.replace(engine.DEFAULT_CONFIG, localized_alteration_rule=False)
    r = engine.compare(fixture_input(ds.docs["dev_alt_src"], None), fixture_input(ds.docs["dev_alt_alt2"], None), v3)
    assert r.outcome == engine.NOT_MATCHED


# --- campus-photo experiment ---------------------------------------------------------------------

def test_campus_dataset_is_synthetic_deterministic_and_separate():
    a, b = campus_dataset(), campus_dataset()
    assert [p.key for p in a] == [p.key for p in b] and all((x.a == y.a).all() for x, y in zip(a, b))
    assert {p.split for p in a} == {"campus_dev", "campus_heldout"} and {p.label for p in a} == {"same_image", "different_building"}


def test_campus_indicator_on_dev_pairs():
    for p in [x for x in campus_dataset() if x.split == "campus_dev"]:
        r = compare_images(p.a, p.b)
        assert r["indicator"] in (POTENTIAL, NOT_INDICATED, INCONCLUSIVE)
        assert (r["indicator"] == POTENTIAL) == (p.label == "same_image"), p.key
        if r["indicator"] == POTENTIAL:
            assert "does not establish institution identity" in r["note"]


def test_campus_evaluation_reports_counts():
    res = evaluate_campus()
    assert res["synthetic"] is True and set(res["metrics"]) == {"campus_dev", "campus_heldout"}
    assert all(m["pairs"] == 6 for m in res["metrics"].values())


# --- physical capture workflow -------------------------------------------------------------------

def test_capture_kit_and_manifest_guards(tmp_path):
    template = physical_capture.write_capture_kit(tmp_path)
    assert template.is_file() and (tmp_path / "ho_ssc_src.pdf").is_file()
    assert physical_capture.status(tmp_path / "manifest.json")["status"] == "BLOCKED"  # nothing captured yet
    data = json.loads(template.read_text(encoding="utf-8"))
    data["entries"][0]["capture"]["kind"] = "simulated"
    (tmp_path / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    st = physical_capture.status(tmp_path / "manifest.json")
    assert st["status"] == "INVALID" and "simulated" in st["reason"]  # simulated can never pass as real
    data["entries"] = data["entries"][:1]
    data["entries"][0]["capture"].update(kind="real_photo", device="", captured_on="")
    (tmp_path / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    assert "device" in physical_capture.status(tmp_path / "manifest.json")["reason"]
    data["entries"][0]["capture"].update(device="phone (test)", captured_on="2026-10-25")
    (tmp_path / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    assert "not found" in physical_capture.status(tmp_path / "manifest.json")["reason"]
    (tmp_path / data["entries"][0]["file"]).write_bytes(b"jpeg bytes")
    assert physical_capture.status(tmp_path / "manifest.json")["status"] == "AVAILABLE"


# --- security / isolation regressions --------------------------------------------------------------

def test_report_and_exports_do_not_leak_linked_cases(client, settings, reviewer):
    from app.services import reuse_fixtures

    with client.app.state.session_factory() as session:
        codes = reuse_fixtures.load(session, client.app.state.document_storage, settings.max_upload_bytes).application_codes
    assert reviewer.post(f"/api/v1/applications/{codes['reuse-app-a']}/cross-case-scans").status_code == 201
    # Error responses for unauthorised pair access carry no linked identities.
    pid = reviewer.get(f"/api/v1/applications/{codes['reuse-app-a']}/cross-case-alerts").json()["items"][0]["pair_id"]
    for path in (f"/api/v1/case-pairs/{pid}", f"/api/v1/case-pairs/{pid}/pages/a/1", "/api/v1/reuse-evaluations"):
        body = reviewer.get(path).text
        assert "Malvan" not in body and codes["reuse-app-b"] not in body
    # The application documents list (visible to all staff) shows only own documents.
    docs = reviewer.get(f"/api/v1/applications/{codes['reuse-app-a']}/documents").text
    assert "Malvan" not in docs and "stability-cert-scaled" not in docs
    # Production scans never set evaluation ground truth.
    from app.models import CasePair
    with client.app.state.session_factory() as session:
        pairs = session.execute(select(CasePair)).scalars().all()
        assert pairs and all(not p.is_evaluation_fixture and p.ground_truth_label is None for p in pairs)


def test_evaluation_exports_contain_only_synthetic_fixtures():
    root = Path(__file__).resolve().parents[2] / "docs" / "evaluation"
    for run in ("reuse-d7", "reuse-d8", "reuse-d9"):
        path = root / run / "metrics.json"
        if not path.is_file():
            continue
        blob = path.read_text(encoding="utf-8")
        assert "REG-EoA-" not in blob and "@Demo" not in blob and "D:\\\\" not in blob
