from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import create_app
from app.schemas.application import ApplicationCreate
from app.services import applications as service
from tests.conftest import application_payload, institution_payload

BASE = "/api/v1/applications"


def status(client: TestClient, code: str, target: str):
    return client.post(f"{BASE}/{code}/status", json={"target_status": target})


# --- creation -------------------------------------------------------------------------------

def test_create_application(client: TestClient, institution: dict) -> None:
    response = client.post(BASE, json=application_payload(institution["institution_code"]))
    assert response.status_code == 201
    body = response.json()
    assert body["application_code"] == "REG-EoA-2026-0001"
    assert body["status"] == "draft"
    assert body["category"] == "extension_of_approval"
    assert body["submitted_at"] is None
    assert body["is_editable"] is True
    assert body["allowed_transitions"] == ["ready_for_preliminary_scrutiny"]
    assert body["institution"]["institution_code"] == institution["institution_code"]
    assert body["institution"]["name"] == institution["name"]
    assert body["programme_count"] == 1 and body["total_proposed_intake"] == 60
    assert body["programmes"][0]["course_name"] == "B.Tech Civil Engineering"
    assert "id" not in body and "institution_id" not in body


def test_application_ids_are_sequential_per_year(client: TestClient, institution: dict) -> None:
    code = institution["institution_code"]
    ids = [client.post(BASE, json=application_payload(code)).json()["application_code"] for _ in range(2)]
    ids.append(client.post(BASE, json=application_payload(code, academic_year="2027-28")).json()["application_code"])
    assert ids == ["REG-EoA-2026-0001", "REG-EoA-2026-0002", "REG-EoA-2027-0001"]


def test_concurrent_creation_produces_unique_ids(tmp_path) -> None:
    from tests.conftest import make_settings

    app = create_app(make_settings(tmp_path / "concurrent.db"))
    with TestClient(app) as c:
        inst_code = c.post("/api/v1/institutions", json=institution_payload()).json()["institution_code"]
    factory = app.state.session_factory
    data = ApplicationCreate.model_validate(application_payload(inst_code))

    def create(_):
        with factory() as session:
            return service.create_application(session, data).application_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(create, range(24)))
    assert len(set(codes)) == 24
    assert sorted(codes) == [f"REG-EoA-2026-{i:04d}" for i in range(1, 25)]


def test_create_with_missing_or_inactive_institution(client: TestClient, institution: dict) -> None:
    missing = client.post(BASE, json=application_payload("INST-99999"))
    assert missing.status_code == 404
    error = missing.json()["error"]
    assert error["code"] == "institution_not_found"
    assert error["details"][0]["loc"] == ["body", "institution_code"]

    code = institution["institution_code"]
    client.patch(f"/api/v1/institutions/{code}", json={"status": "inactive"})
    inactive = client.post(BASE, json=application_payload(code))
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "institution_inactive"


@pytest.mark.parametrize("year", ["2026-28", "2026", "26-27", "1999-00", "2026/27", "abcd-ef"])
def test_invalid_academic_year_rejected(client: TestClient, institution: dict, year: str) -> None:
    response = client.post(BASE, json=application_payload(institution["institution_code"], academic_year=year))
    assert response.status_code == 422
    assert any("academic_year" in d["loc"] for d in response.json()["error"]["details"])


def test_century_rollover_academic_year_accepted(client: TestClient, institution: dict) -> None:
    response = client.post(BASE, json=application_payload(institution["institution_code"], academic_year="2099-00"))
    assert response.status_code == 201


@pytest.mark.parametrize("intake", [-1, 601, "60", 60.5, None])
def test_invalid_intake_rejected(client: TestClient, institution: dict, intake) -> None:
    programmes = [{"programme_level": "undergraduate", "course_name": "B.Tech IT",
                   "existing_intake": 60, "proposed_intake": intake}]
    response = client.post(BASE, json=application_payload(institution["institution_code"], programmes=programmes))
    assert response.status_code == 422


def test_business_rules_for_programmes(client: TestClient, institution: dict) -> None:
    code = institution["institution_code"]
    prog = lambda e, p, name="B.Tech IT": {"programme_level": "undergraduate", "course_name": name,
                                          "existing_intake": e, "proposed_intake": p}
    bad = [
        ("increase_in_intake", [prog(60, 60)]),
        ("reduction_in_intake", [prog(60, 90)]),
        ("introduction_of_new_course", [prog(60, 60)]),
        ("eoa_no_change", [prog(60, 90)]),
        ("eoa_no_change", [prog(60, 60), prog(60, 60)]),  # duplicate programme
        ("eoa_no_change", []),
    ]
    for app_type, programmes in bad:
        response = client.post(BASE, json=application_payload(code, application_type=app_type, programmes=programmes))
        assert response.status_code == 422, (app_type, programmes)
    ok = client.post(BASE, json=application_payload(code, application_type="introduction_of_new_course",
                                                     programmes=[prog(60, 60), prog(0, 30, "B.Tech AI")]))
    assert ok.status_code == 201


def test_client_cannot_set_status_or_code_on_create(client: TestClient, institution: dict) -> None:
    for extra in ({"status": "preliminary_scrutiny_completed"}, {"application_code": "REG-EoA-2026-9999"},
                  {"submitted_at": "2026-01-01T00:00:00Z"}):
        response = client.post(BASE, json=application_payload(institution["institution_code"], **extra))
        assert response.status_code == 422, extra


# --- listing --------------------------------------------------------------------------------

@pytest.fixture
def populated(client: TestClient) -> dict:
    a = client.post("/api/v1/institutions", json=institution_payload(name="Alpha Synthetic College")).json()
    b = client.post("/api/v1/institutions", json=institution_payload(name="Bravo Synthetic Institute")).json()
    up = lambda e, p: [{"programme_level": "undergraduate", "course_name": "B.Tech IT",
                        "existing_intake": e, "proposed_intake": p}]
    specs = [
        (a, "2026-27", "eoa_no_change", up(60, 60)),
        (a, "2025-26", "increase_in_intake", up(60, 120)),
        (b, "2026-27", "reduction_in_intake", up(120, 60)),
        (b, "2026-27", "eoa_no_change", up(60, 60)),
        (b, "2027-28", "eoa_no_change", up(60, 60)),
    ]
    codes = [client.post(BASE, json=application_payload(i["institution_code"], academic_year=y,
                                                        application_type=t, programmes=p)).json()["application_code"]
             for i, y, t, p in specs]
    status(client, codes[3], "ready_for_preliminary_scrutiny")
    return {"a": a, "b": b, "codes": codes}


def test_list_pagination_and_stable_order(client: TestClient, populated: dict) -> None:
    page1 = client.get(BASE, params={"page_size": 2}).json()
    page2 = client.get(BASE, params={"page_size": 2, "page": 2}).json()
    page3 = client.get(BASE, params={"page_size": 2, "page": 3}).json()
    assert (page1["total"], page1["total_pages"]) == (5, 3)
    listed = [i["application_code"] for p in (page1, page2, page3) for i in p["items"]]
    assert len(set(listed)) == 5
    assert listed == sorted(populated["codes"], key=lambda c: populated["codes"].index(c), reverse=True)
    item = page1["items"][0]
    assert item["institution"]["name"] and "programmes" not in item
    assert client.get(BASE, params={"page_size": 500}).status_code == 422


def test_filters(client: TestClient, populated: dict) -> None:
    def codes(**params):
        return {i["application_code"] for i in client.get(BASE, params=params).json()["items"]}

    c = populated["codes"]
    assert codes(status="ready_for_preliminary_scrutiny") == {c[3]}
    assert codes(status="draft") == {c[0], c[1], c[2], c[4]}
    assert codes(academic_year="2026-27") == {c[0], c[2], c[3]}
    assert codes(application_type="increase_in_intake") == {c[1]}
    assert codes(institution_code=populated["a"]["institution_code"]) == {c[0], c[1]}
    assert codes(institution_code=populated["b"]["institution_code"], academic_year="2026-27") == {c[2], c[3]}
    assert client.get(BASE, params={"status": "approved"}).status_code == 422
    assert client.get(BASE, params={"academic_year": "bad"}).status_code == 422


def test_search(client: TestClient, populated: dict) -> None:
    def codes(q):
        return {i["application_code"] for i in client.get(BASE, params={"q": q}).json()["items"]}

    c = populated["codes"]
    assert codes("bravo") == {c[2], c[3], c[4]}
    assert codes(populated["a"]["institution_code"].lower()) == {c[0], c[1]}
    assert codes("REG-EoA-2027") == {c[4]}
    assert codes("no-such-thing") == set()


def test_list_avoids_n_plus_one(client: TestClient, populated: dict, app) -> None:
    statements: list[str] = []
    listener = lambda conn, cursor, statement, *a: statements.append(statement)
    event.listen(app.state.engine, "before_cursor_execute", listener)
    try:
        assert client.get(BASE, params={"page_size": 100}).json()["total"] == 5
    finally:
        event.remove(app.state.engine, "before_cursor_execute", listener)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 3, selects  # count + page (with institution join) + programmes selectin


# --- detail, updates, workflow --------------------------------------------------------------

def test_detail_and_not_found(client: TestClient, draft: dict) -> None:
    assert client.get(f"{BASE}/{draft['application_code']}").json() == draft
    response = client.get(f"{BASE}/REG-EoA-2026-9999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_draft_update(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    response = client.patch(f"{BASE}/{code}", json={
        "academic_year": "2027-28",
        "application_type": "increase_in_intake",
        "programmes": [
            {"programme_level": "undergraduate", "course_name": "B.Tech Civil Engineering",
             "existing_intake": 60, "proposed_intake": 90},
            {"programme_level": "postgraduate", "course_name": "M.Tech Structures",
             "existing_intake": 18, "proposed_intake": 18},
        ],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application_code"] == code  # ID is never regenerated
    assert body["academic_year"] == "2027-28"
    assert body["programme_count"] == 2 and body["total_proposed_intake"] == 108
    assert body["updated_at"] > draft["updated_at"]


def test_failed_update_leaves_record_unchanged(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    # Valid year but programmes violate the new type's rule -> whole update rejected.
    response = client.patch(f"{BASE}/{code}", json={"academic_year": "2027-28", "application_type": "increase_in_intake"})
    assert response.status_code == 422
    assert client.get(f"{BASE}/{code}").json() == draft
    response = client.patch(f"{BASE}/{code}", json={"academic_year": "2027-28", "institution_code": "INST-99999"})
    assert response.status_code == 404
    assert client.get(f"{BASE}/{code}").json() == draft


def test_update_rejects_protected_fields(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    for body in ({"status": "preliminary_scrutiny_completed"}, {"application_code": "X"},
                 {"created_at": "2020-01-01T00:00:00Z"}, {"academic_year": None}):
        assert client.patch(f"{BASE}/{code}", json=body).status_code == 422, body


def test_frozen_application_cannot_be_edited(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    ready = status(client, code, "ready_for_preliminary_scrutiny").json()
    assert ready["is_editable"] is False
    assert ready["submitted_at"] is not None
    assert ready["institution_snapshot"]["name"] == draft["institution"]["name"]
    response = client.patch(f"{BASE}/{code}", json={"academic_year": "2027-28"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_frozen"
    assert client.get(f"{BASE}/{code}").json()["academic_year"] == "2026-27"


def test_valid_transition_path(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    for target, allowed in [
        ("ready_for_preliminary_scrutiny", ["draft", "under_preliminary_scrutiny"]),
        ("under_preliminary_scrutiny", ["awaiting_additional_evidence", "preliminary_scrutiny_completed"]),
        ("awaiting_additional_evidence", ["under_preliminary_scrutiny"]),
        ("under_preliminary_scrutiny", ["awaiting_additional_evidence", "preliminary_scrutiny_completed"]),
        ("preliminary_scrutiny_completed", []),
    ]:
        response = status(client, code, target)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
        assert response.json()["allowed_transitions"] == allowed


def test_return_to_draft_reopens_editing(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    status(client, code, "ready_for_preliminary_scrutiny")
    body = status(client, code, "draft").json()
    assert body["is_editable"] is True and body["submitted_at"] is None and body["institution_snapshot"] is None
    assert client.patch(f"{BASE}/{code}", json={"academic_year": "2027-28"}).status_code == 200


@pytest.mark.parametrize("target", ["under_preliminary_scrutiny", "preliminary_scrutiny_completed",
                                    "awaiting_additional_evidence", "draft"])
def test_invalid_transitions_from_draft(client: TestClient, draft: dict, target: str) -> None:
    response = status(client, draft["application_code"], target)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_status_transition"
    assert error["details"] == [{"allowed_transitions": ["ready_for_preliminary_scrutiny"]}]


def test_status_values_cannot_imply_aicte_decision(client: TestClient, draft: dict) -> None:
    for target in ("approved", "rejected", "fraud"):
        assert status(client, draft["application_code"], target).status_code == 422


def test_completed_is_terminal(client: TestClient, draft: dict) -> None:
    code = draft["application_code"]
    for t in ("ready_for_preliminary_scrutiny", "under_preliminary_scrutiny", "preliminary_scrutiny_completed"):
        status(client, code, t)
    assert status(client, code, "under_preliminary_scrutiny").status_code == 409


def test_institution_edit_does_not_rewrite_frozen_snapshot(client: TestClient, draft: dict) -> None:
    code, inst = draft["application_code"], draft["institution"]["institution_code"]
    status(client, code, "ready_for_preliminary_scrutiny")
    client.patch(f"/api/v1/institutions/{inst}", json={"name": "Completely New Synthetic Name"})
    body = client.get(f"{BASE}/{code}").json()
    assert body["institution"]["name"] == "Completely New Synthetic Name"
    assert body["institution_snapshot"]["name"] == draft["institution"]["name"]


def test_persistence_across_sessions_and_restarts(tmp_path) -> None:
    from tests.conftest import make_settings

    settings = make_settings(tmp_path / "persist.db")
    with TestClient(create_app(settings)) as c1:
        inst = c1.post("/api/v1/institutions", json=institution_payload()).json()
        created = c1.post(BASE, json=application_payload(inst["institution_code"])).json()
    with TestClient(create_app(settings)) as c2:  # new engine, new sessions, same file
        assert c2.get(f"{BASE}/{created['application_code']}").json() == created
        nxt = c2.post(BASE, json=application_payload(inst["institution_code"])).json()
        assert nxt["application_code"] == "REG-EoA-2026-0002"
