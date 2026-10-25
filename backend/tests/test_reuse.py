"""Cross-case document reuse: cascade stages, decisions, persistence, access control, dispositions, evaluation."""

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import AppError
from app.models import AuditEvent, CasePair, Document, MatchEvidence, ReuseScanRun, User
from app.models.enums import ReuseScanStatus
from app.services import reuse, reuse_engine as engine, reuse_eval, reuse_fixtures, reuse_visual as visual
from app.services.reuse_dataset import Dataset, build_dataset
from tests.conftest import authenticate


@pytest.fixture(scope="module")
def ds() -> Dataset:
    return build_dataset()


@pytest.fixture(scope="module")
def inputs(ds):
    cache = {}

    def get(key):
        if key not in cache:
            cache[key] = reuse_eval.fixture_input(ds.docs[key], None)
        return cache[key]
    return get


# --- L0 / L1 ---------------------------------------------------------------------------------------

def test_exact_duplicate_across_cases_is_confirmed_as_byte_identity(inputs):
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_fire_exact"))
    assert r.outcome == engine.MATCH_CONFIRMED
    assert r.exact["equal"] and "exact_sha256" in r.candidate_methods
    assert any("authenticity" in u for u in r.uncertainties)


def test_text_normalisation_is_conservative():
    text = engine.normalize_text("Certificate No.:  SYN-VFS/2026/0418\n\nIssue​ Date: 12-02-2026")
    assert text == "certificate no.: syn-vfs/2026/0418 issue date: 12-02-2026"  # identifiers and punctuation kept


def test_empty_or_unreadable_text_is_unavailable_not_a_match(inputs):
    t = engine.text_stage(inputs("dev_blank_a"), inputs("dev_blank_b"), engine.DEFAULT_CONFIG)
    assert t["status"] == "unavailable" and "could not be read" in t["reason"]
    r = engine.compare(inputs("dev_blank_a"), inputs("dev_blank_b"))
    assert r.outcome == engine.INCONCLUSIVE


# --- L2 / L3 ---------------------------------------------------------------------------------------

def test_phash_retrieves_rescaled_and_rotated_copies(inputs):
    v = engine.visual_stage(inputs("dev_fire_src"), inputs("dev_fire_vec"), engine.DEFAULT_CONFIG)
    assert v["status"] == "computed" and v["distance"] <= engine.DEFAULT_CONFIG.phash_candidate
    assert v["rotation_b_degrees"] in (90, 270)


def test_geometric_verification_success_records_metrics(ds):
    g = engine.finalize_geometry(visual.geometric_verify(ds.docs["dev_fire_src"].pdf, 1, ds.docs["dev_fire_vec"].pdf, 1,
                                                         engine.DEFAULT_CONFIG.visual), engine.DEFAULT_CONFIG)
    assert g["status"] == "verified" and g["detector"] == "ORB" and g["opencv_version"]
    assert g["inliers"] >= engine.DEFAULT_CONFIG.min_inliers and 0 < g["inlier_ratio"] <= 1
    assert g["coverage"] >= engine.DEFAULT_CONFIG.min_coverage and g["transform"]["type"] == "homography"
    assert g["differences"]["cells_different"] == 0  # same content after alignment


def test_geometric_verification_failure_on_unrelated_body(ds):
    g = engine.finalize_geometry(visual.geometric_verify(ds.docs["dev_fire_src"].pdf, 1, ds.docs["dev_letter"].pdf, 1,
                                                         engine.DEFAULT_CONFIG.visual), engine.DEFAULT_CONFIG)
    assert g["status"] == "not_verified" and g["reason"]


def test_geometric_verification_unsupported_input_is_inconclusive(ds):
    g = visual.geometric_verify(ds.docs["dev_blank_a"].pdf, 1, ds.docs["dev_blank_b"].pdf, 1, engine.DEFAULT_CONFIG.visual)
    assert g["status"] == "inconclusive" and "keypoints" in g["reason"]


def test_geometric_verification_reports_missing_opencv(ds, monkeypatch):
    monkeypatch.setattr(visual, "cv2", None)
    g = visual.geometric_verify(ds.docs["dev_fire_src"].pdf, 1, ds.docs["dev_fire_vec"].pdf, 1, engine.DEFAULT_CONFIG.visual)
    assert g["status"] == "unavailable" and "OpenCV" in g["reason"]


def test_localized_difference_is_found_on_controlled_alteration(inputs):
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_fire_alter"))
    assert r.geometric["status"] == "verified" and r.geometric["differences"]["cells_different"] >= 1
    assert r.fields["conflict"] == 1
    assert r.outcome == engine.CANDIDATE  # possible alteration for review, never "confirmed"


# --- decisions -------------------------------------------------------------------------------------

def test_transformed_positive_with_text_layer_is_confirmed(inputs):
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_fire_vec"))
    assert r.outcome == engine.MATCH_CONFIRMED and r.fields["agree"] >= 2 and r.fields["conflict"] == 0


def test_same_template_hard_negatives_are_not_confirmed(inputs):
    # Different institution, number and dates on the same template: no shared content.
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_fire_tmpl"))
    assert r.outcome == engine.NOT_MATCHED and r.fields["conflict"] >= 2 and r.fields["agree"] == 0
    # Same institution, earlier certificate (number and dates differ only on their lines): since v4 this is a review
    # candidate — by evidence it cannot be told apart from a number-and-date alteration — and never a confirmation.
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_fire_renew"))
    assert r.outcome == engine.CANDIDATE and r.fields["conflict"] >= 2
    assert "different certificate issued on the same template" in r.fusion["rule"]


def test_similar_logo_with_unrelated_content_is_not_matched(inputs):
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_letter"))
    assert r.outcome == engine.NOT_MATCHED


def test_raster_copy_without_ocr_stays_candidate_with_stated_uncertainty(inputs):
    r = engine.compare(inputs("dev_fire_src"), inputs("dev_fire_scan"))
    assert r.outcome == engine.CANDIDATE
    assert r.text["status"] == "unavailable" and r.fields["inconclusive"] >= 1 and r.fields["conflict"] == 0
    assert any("OCR" in u or "readable text" in u for u in r.uncertainties)


def test_field_comparison_states():
    page = engine.PageText(1, "Certificate No.: A-1\nDate of Issue: 12 March 2026\nName of Institution: X College")

    def doc(fields, pages=(page,)):
        return engine.DocumentInput("d", "c", "0" * 64, b"", list(pages), fields)

    f = lambda name, raw, norm, quote, status="extracted": engine.FieldEvidence(name, raw, norm, 1, quote, status)  # noqa: E731
    a = doc([f("certificate_number", "A-1", {"text": "A1"}, "Certificate No.: A-1"),
             f("issue_date", "12 March 2026", {"date": "2026-03-12"}, "Date of Issue: 12 March 2026"),
             f("institution_name", "X College", {"text": "x college"}, "Name of Institution: X College")])
    other_page = engine.PageText(1, "Certificate No.: A-2\nDate of Issue: 12 March 2026")
    b = doc([f("certificate_number", "A-2", {"text": "A2"}, "Certificate No.: A-2"),
             f("issue_date", "12 March 2026", {"date": "2026-03-12"}, "Date of Issue: 12 March 2026"),
             f("institution_name", "X College", {"text": "x college"}, "Name of Institution: X College")],
            pages=(other_page,))
    result = {c["field"]: c for c in engine.field_stage(a, b)["comparisons"]}
    assert result["certificate_number"]["outcome"] == "conflict"
    assert result["issue_date"]["outcome"] == "agree"
    # B's institution quote is not in B's page text → no valid source pointer → inconclusive, never a conflict
    assert result["institution_name"]["outcome"] == "inconclusive"
    c = doc([f("certificate_number", None, None, None, status="not_found")])
    missing = {x["field"]: x for x in engine.field_stage(a, c)["comparisons"]}
    assert missing["certificate_number"]["outcome"] == "inconclusive"
    assert "not a conflict" in missing["certificate_number"]["explanation"]


# --- evaluation ------------------------------------------------------------------------------------

def test_ratio_handles_zero_denominator():
    assert reuse_eval.ratio(0, 0, "predicted positives") == {"value": None, "numerator": 0, "denominator": 0,
                                                             "note": "undefined: no predicted positives"}
    assert reuse_eval.ratio(3, 4, "x")["value"] == 0.75


def test_confusion_counts_and_excludes_altered_pairs():
    rows = [
        {"label": "reuse", "hard_negative": False, "A": {"positive": True, "latency_ms": 1}},
        {"label": "reuse", "hard_negative": False, "A": {"positive": False, "latency_ms": 1}},
        {"label": "distinct", "hard_negative": True, "A": {"positive": True, "latency_ms": 1}},
        {"label": "distinct", "hard_negative": False, "A": {"positive": False, "latency_ms": 1}},
        {"label": "altered", "hard_negative": False, "A": {"positive": True, "latency_ms": 1}},
    ]
    m = reuse_eval.confusion(rows, "A")
    assert (m["tp"], m["fp"], m["tn"], m["fn"], m["pairs"]) == (1, 1, 1, 1, 4)
    assert m["precision"]["value"] == 0.5 and m["recall"]["value"] == 0.5
    assert m["hard_negative_fp"] == 1 and m["hard_negative_fp_rate"]["denominator"] == 1


def test_arms_use_the_same_pairs_and_report_traceability(ds):
    keep = {"dev_p01", "dev_p03", "dev_p06", "dev_p10"}
    small = Dataset(ds.version, ds.docs, [p for p in ds.pairs if p.key in keep])
    data = reuse_eval.evaluate(small, splits=("dev",)).data
    assert {r["pair"] for r in data["pairs"]} == keep
    assert all({"A0", "A1", "A4"} <= set(r) for r in data["pairs"])
    m = data["metrics"]["dev"]
    assert m["A0"]["pairs"] == m["A1"]["pairs"] == m["A4"]["pairs"] == 3  # altered pair excluded from binary counts
    assert m["A4"]["tp"] == 2 and m["A4"]["fp"] == 0 and m["A0"]["tp"] == 1
    t = data["evidence_traceability"]
    assert t["denominator"] > 0 and t["numerator"] == t["denominator"]
    csv_text = reuse_eval.EvalResult(data).to_csv()
    assert csv_text.startswith("split,arm,tp,fp,tn,fn") and "dev_p10" in csv_text
    assert "no statistical significance" in reuse_eval.EvalResult(data).to_markdown()


def test_dataset_is_deterministic_and_splits_are_disjoint(ds):
    again = build_dataset()
    assert {k: d.pdf for k, d in ds.docs.items()} == {k: d.pdf for k, d in again.docs.items()}
    dev_docs = {k for p in ds.pairs if p.split == "dev" for k in (p.a, p.b)}
    held_docs = {k for p in ds.pairs if p.split == "heldout" for k in (p.a, p.b)}
    assert not dev_docs & held_docs
    comp = ds.composition()
    assert comp["pairs"]["heldout"]["hard_negative"] >= 5 and comp["pairs"]["dev"]["reuse"] >= 3


# --- integration: scans, persistence, access control -------------------------------------------------

@pytest.fixture
def fixtures_loaded(client: TestClient, settings):
    app = client.app
    with app.state.session_factory() as session:
        res = reuse_fixtures.load(session, app.state.document_storage, settings.max_upload_bytes)
    return res.application_codes


@pytest.fixture
def scanned(client: TestClient, fixtures_loaded, reviewer: TestClient):
    r = reviewer.post(f"/api/v1/applications/{fixtures_loaded['reuse-app-a']}/cross-case-scans")
    assert r.status_code == 201, r.text
    return fixtures_loaded, r.json()


def _senior(app) -> TestClient:
    c = TestClient(app, raise_server_exceptions=False)
    c.__enter__()
    authenticate(c, "reviewer", username="senior.reviewer")
    with app.state.session_factory() as session:
        user = session.execute(select(User).where(User.username == "senior.reviewer")).scalar_one()
        user_id = user.id
    return c, user_id


def _grant(client: TestClient, senior: TestClient, user_id: str) -> TestClient:
    r = client.patch(f"/api/v1/users/{user_id}", json={"cross_case_reviewer": True})
    assert r.status_code == 200 and r.json()["cross_case_reviewer"] is True
    authenticate(senior, "reviewer", username="senior.reviewer")  # permission change revokes sessions
    return senior


def _pairs(app) -> dict[str, CasePair]:
    with app.state.session_factory() as session:
        rows = session.execute(select(CasePair)).scalars().all()
        out = {}
        for p in rows:
            out[p.evidence.snapshot["b"]["filename"]] = p
            session.expunge(p)
        return out


def test_scan_finds_transformed_positive_and_keeps_hard_negative_unconfirmed(client, scanned):
    _, run = scanned
    assert run["status"] == "completed" and run["candidates"] >= 3 and run["pairs_created"] == run["candidates"]
    pairs = _pairs(client.app)
    assert pairs["stability-cert-scaled.pdf"].outcome.value == "MATCH_CONFIRMED_FOR_REVIEW"
    assert pairs["structural-certificate-scan.pdf"].outcome.value == "CANDIDATE"
    assert pairs["structural-stability-2025.pdf"].outcome.value == "NOT_MATCHED"
    with client.app.state.session_factory() as session:
        ev = session.execute(select(MatchEvidence).where(
            MatchEvidence.pair_id == pairs["stability-cert-scaled.pdf"].id)).scalar_one()
        assert ev.geometric["status"] == "verified" and ev.text["status"] == "computed"
        assert ev.config["version"] == engine.DEFAULT_CONFIG.version and ev.stage_status["geometric"] == "verified"


def test_rerun_reuses_pairs_and_new_config_creates_new_snapshot(client, scanned, settings):
    codes, _ = scanned
    again = client.post(f"/api/v1/applications/{codes['reuse-app-a']}/cross-case-scans").json()
    assert again["pairs_created"] == 0 and again["pairs_reused"] == again["candidates"]
    before = len(_pairs(client.app))
    app = client.app
    with app.state.session_factory() as session:
        from app.core.context import SYSTEM_ACTOR
        cfg = dataclasses.replace(engine.DEFAULT_CONFIG, version="reuse_thr_test_only")
        run = reuse.run_scan(session, app.state.document_storage, settings, None, codes["reuse-app-a"], SYSTEM_ACTOR, cfg)
        assert run.pairs_created == run.candidates > 0
        total = session.execute(select(CasePair)).scalars().all()
        assert len(total) == before + run.pairs_created  # history kept; earlier evaluations not rewritten


def test_concurrent_scan_is_refused(client, fixtures_loaded):
    app = client.app
    with app.state.session_factory() as session:
        from app.models import Application
        a = session.execute(select(Application).where(Application.application_code == fixtures_loaded["reuse-app-a"])).scalar_one()
        session.add(ReuseScanRun(application_id=a.id, status=ReuseScanStatus.RUNNING, pipeline_version="x",
                                 config_version="x", config={}, triggered_by="test", outcome_counts={}))
        session.commit()
    r = client.post(f"/api/v1/applications/{fixtures_loaded['reuse-app-a']}/cross-case-scans")
    assert r.status_code == 409 and r.json()["error"]["code"] == "scan_in_progress"


def test_ordinary_reviewer_sees_only_a_restricted_alert(client, scanned, reviewer):
    codes, _ = scanned
    r = reviewer.get(f"/api/v1/applications/{codes['reuse-app-a']}/cross-case-alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["can_view_details"] is False and body["items"]
    assert all(i["restricted"] and i["linked"] is None for i in body["items"])
    text = r.text
    linked_doc_ids = [p.document_b_id for p in _pairs(client.app).values()]
    for leaked in ("Malvan", "Dapoli", "stability-cert-scaled", "structural-certificate-scan", *linked_doc_ids):
        assert leaked not in text
    # The global alert list (visible to all staff) does not leak the linked case either.
    alerts_text = reviewer.get("/api/v1/alerts", params={"page_size": 100}).text
    assert "Possible cross-case document reuse" in alerts_text and "Malvan" not in alerts_text


def test_detail_endpoints_deny_without_permission_and_are_audited(client, scanned, reviewer):
    pair = _pairs(client.app)["stability-cert-scaled.pdf"]
    paths = [("get", f"/api/v1/case-pairs/{pair.id}"), ("get", f"/api/v1/case-pairs/{pair.id}/pages/b/1"),
             ("get", f"/api/v1/case-pairs/{pair.id}/review-actions"), ("get", "/api/v1/case-pairs")]
    for method, path in paths:
        for c in (reviewer, client):  # the admin role alone does not grant cross-case details
            r = getattr(c, method)(path)
            assert r.status_code == 403, (path, r.text)
            assert r.json()["error"]["code"] == "cross_case_permission_required"
            assert "Malvan" not in r.text
    r = reviewer.post(f"/api/v1/case-pairs/{pair.id}/review-actions",
                      json={"action": "dismiss", "note": "trying without permission", "expected_version": 1})
    assert r.status_code == 403
    with client.app.state.session_factory() as session:
        denied = session.execute(select(AuditEvent).where(AuditEvent.action == "cross_case.access_denied")).scalars().all()
        assert len(denied) >= 9
        assert any(e.details.get("pair_id") == pair.id and e.actor_username == "test.reviewer" for e in denied)
        assert all("Malvan" not in json.dumps(e.details) for e in denied)


def test_authorised_reviewer_gets_details_images_and_audited_access(client, scanned):
    senior, user_id = _senior(client.app)
    try:
        assert senior.get("/api/v1/case-pairs").status_code == 403
        _grant(client, senior, user_id)
        pair = _pairs(client.app)["stability-cert-scaled.pdf"]
        r = senior.get(f"/api/v1/case-pairs/{pair.id}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["b"]["institution_name"] == "Malvan Bay Institute of Technology" and d["a"]["application_code"]
        assert d["evidence"]["geometric"]["status"] == "verified"
        assert any(c["outcome"] == "agree" for c in d["evidence"]["fields"]["comparisons"])
        assert "not automatically misconduct" in d["notice"]
        img = senior.get(f"/api/v1/case-pairs/{pair.id}/pages/b/1")
        assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
        assert senior.get(f"/api/v1/case-pairs/{pair.id}/pages/b/9").status_code == 404
        listing = senior.get("/api/v1/case-pairs", params={"outcome": "MATCH_CONFIRMED_FOR_REVIEW"}).json()
        assert listing["total"] >= 1
        alerts = senior.get(f"/api/v1/applications/{scanned[0]['reuse-app-a']}/cross-case-alerts").json()
        assert alerts["can_view_details"] and any(i["linked"] for i in alerts["items"])
        with client.app.state.session_factory() as session:
            actions = {e.action for e in session.execute(select(AuditEvent).where(
                AuditEvent.actor_username == "senior.reviewer")).scalars()}
            assert {"cross_case.pair_viewed", "cross_case.page_image_viewed"} <= actions
    finally:
        senior.__exit__(None, None, None)


def test_admin_cannot_grant_cross_case_permission_to_self(client):
    me = client.get("/api/v1/auth/me").json()
    r = client.patch(f"/api/v1/users/{me['id']}", json={"cross_case_reviewer": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_permission_change"


def test_reviewer_disposition_is_stored_separately_from_evidence(client, scanned):
    senior, user_id = _senior(client.app)
    try:
        _grant(client, senior, user_id)
        pair = _pairs(client.app)["structural-certificate-scan.pdf"]
        base = f"/api/v1/case-pairs/{pair.id}/review-actions"
        before = senior.get(f"/api/v1/case-pairs/{pair.id}").json()["evidence"]
        r = senior.post(base, json={"action": "dismiss", "note": "short", "expected_version": 1})
        assert r.status_code == 422
        r = senior.post(base, json={"action": "confirm_candidate", "note": "Seal, layout and body align; request "
                                    "the original from both institutions.", "expected_version": 1})
        assert r.status_code == 201 and r.json()["review_status"] == "confirmed_candidate"
        assert r.json()["evidence"] == before  # system evidence unchanged
        assert senior.post(base, json={"action": "escalate", "note": "stale attempt here", "expected_version": 1}
                           ).status_code == 409
        r = senior.post(base, json={"action": "note", "note": "Scanned copy; OCR was unavailable.", "expected_version": 2})
        assert r.status_code == 201 and r.json()["review_status"] == "confirmed_candidate"
        history = senior.get(base).json()
        assert [h["action_type"] for h in history] == ["confirm_candidate", "note"]
        assert history[0]["actor_username"] == "senior.reviewer"
        with client.app.state.session_factory() as session:
            ev = session.execute(select(AuditEvent).where(AuditEvent.action == "cross_case.review_action")).scalars().all()
            assert len(ev) == 2 and all(e.details["pair_id"] == pair.id for e in ev)
            assert all("note" not in e.details for e in ev)
    finally:
        senior.__exit__(None, None, None)


def test_same_file_within_one_case_keeps_existing_duplicate_policy(client, code, settings):
    from tests.test_documents import upload  # existing helper

    pdf = build_dataset().docs["dev_fire_src"].pdf
    first = upload(client, code, pdf, name="one.pdf")
    second = upload(client, code, pdf, name="two.pdf")
    assert second.json()["status"] == "duplicate_detected" and second.json()["duplicate_of"]["id"] == first.json()["id"]
    run = client.post(f"/api/v1/applications/{code}/cross-case-scans").json()
    assert run["status"] == "completed" and run["candidates"] == 0  # within-case duplicates are not cross-case pairs


def test_evaluation_endpoints_permissions_and_exports(client, reviewer, ds, monkeypatch):
    small = Dataset(ds.version, ds.docs, [p for p in ds.pairs if p.key in {"dev_p01", "dev_p06"}])
    real = reuse_eval.evaluate
    monkeypatch.setattr(reuse_eval, "evaluate", lambda **kw: real(small, splits=("dev",)))
    assert reviewer.post("/api/v1/reuse-evaluations").status_code == 403
    r = client.post("/api/v1/reuse-evaluations")
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert r.json()["results"]["metrics"]["dev"]["A0"]["tp"] == 1
    assert client.get("/api/v1/reuse-evaluations").json()[0]["id"] == eid
    csv_r = client.get(f"/api/v1/reuse-evaluations/{eid}/export", params={"format": "csv"})
    assert csv_r.status_code == 200 and csv_r.text.startswith("split,arm")
    md = client.get(f"/api/v1/reuse-evaluations/{eid}/export", params={"format": "md"})
    assert "A4" in md.text
    assert reviewer.get(f"/api/v1/reuse-evaluations/{eid}").status_code == 403


def test_fixture_reset_is_guarded_and_removes_only_fixture_cases(client, fixtures_loaded, settings, code):
    app = client.app
    with app.state.session_factory() as session:
        with pytest.raises(reuse_fixtures.FixtureResetRefused):
            reuse_fixtures.reset(session, settings, confirm=False)
        from tests.conftest import make_settings
        prod = make_settings(settings.sqlite_path, environment="production", demo_users_enabled=False)
        with pytest.raises(reuse_fixtures.FixtureResetRefused):
            reuse_fixtures.reset(session, prod, confirm=True)
        removed = reuse_fixtures.reset(session, settings, confirm=True)
        assert removed == 4
        from app.models import Application
        codes = set(session.execute(select(Application.application_code)).scalars())
        assert code in codes and not (set(fixtures_loaded.values()) & codes)
        assert session.execute(select(Document).where(Document.seed_key.like("reuse-%"))).first() is None


def test_migration_0007_upgrades_existing_database_and_round_trips(tmp_path):
    import sqlite3

    from sqlalchemy import create_engine

    from app.db.init_db import run_migrations
    from app.services import auth as auth_service
    from app.models.enums import UserRole
    from app.db.session import build_session_factory

    db = tmp_path / "old.db"
    engine_ = create_engine(f"sqlite:///{db.as_posix()}")
    run_migrations(engine_, "0006")
    factory = build_session_factory(engine_)
    with factory() as session:  # a pre-0007 user row written with the old schema
        session.execute(__import__("sqlalchemy").text(
            "INSERT INTO users (id, username, display_name, role, password_hash, is_active, created_at, updated_at) "
            "VALUES ('u-old', 'old.reviewer', 'Old Reviewer', 'reviewer', 'x', 1, '2026-01-01', '2026-01-01')"))
        session.commit()
    run_migrations(engine_, "head")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0009",)
        assert conn.execute("SELECT username, cross_case_reviewer FROM users").fetchall() == [("old.reviewer", 0)]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"case_pairs", "match_evidence", "case_pair_review_actions", "reuse_scan_runs",
                "document_fingerprints", "reuse_evaluation_runs"} <= tables
    from alembic import command
    from app.db.init_db import alembic_config
    cfg = alembic_config()
    with engine_.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0006")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone() == (1,)
        assert "case_pairs" not in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    run_migrations(engine_, "head")
    engine_.dispose()


def _ev(**over):
    base = dict(exact={"equal": False}, text={"status": "unavailable", "reason": "no text"},
                vis={"status": "computed", "distance": 6, "page_a": 1, "page_b": 1, "rotation_b_degrees": 0},
                geo={"status": "verified", "inliers": 800, "tentative_matches": 900, "coverage": 0.7,
                     "differences": {"cells_different": 0, "cells_judged": 80}},
                fields={"comparisons": [], "agree": 0, "conflict": 0, "inconclusive": 3})
    base.update(over)
    return base


def test_v2_layout_only_similarity_is_not_a_candidate():
    cfg = engine.DEFAULT_CONFIG
    many = _ev(geo={"status": "verified", "inliers": 800, "tentative_matches": 900, "coverage": 0.7,
                    "differences": {"cells_different": cfg.max_diff_regions_shared + 1, "cells_judged": 80}})
    outcome, reasons, _ = engine.decide(many["exact"], many["text"], many["vis"], many["geo"], many["fields"], cfg)
    assert outcome == engine.NOT_MATCHED and any("layout similarity alone" in r for r in reasons)
    few = _ev(geo={**many["geo"], "differences": {"cells_different": 2, "cells_judged": 80}})
    assert engine.decide(few["exact"], few["text"], few["vis"], few["geo"], few["fields"], cfg)[0] == engine.CANDIDATE


def test_v2_unrelated_text_outweighs_a_single_conflicting_field():
    cfg = engine.DEFAULT_CONFIG
    # Geometry verified with a few local differences (still "strong visual"): v1 called this a possible alteration.
    e = _ev(text={"status": "computed", "jaccard": 0.3, "containment": 0.5},
            geo={"status": "verified", "inliers": 800, "tentative_matches": 900, "coverage": 0.7,
                 "differences": {"cells_different": 3, "cells_judged": 80}},
            fields={"comparisons": [], "agree": 0, "conflict": 1, "inconclusive": 2})
    outcome, reasons, _ = engine.decide(e["exact"], e["text"], e["vis"], e["geo"], e["fields"], cfg)
    assert outcome == engine.NOT_MATCHED and any("body text differs" in r for r in reasons)
