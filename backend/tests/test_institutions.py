from fastapi.testclient import TestClient

from tests.conftest import institution_payload

BASE = "/api/v1/institutions"


def test_create_institution(client: TestClient) -> None:
    response = client.post(BASE, json=institution_payload(name="  Alpha   Synthetic College  "))
    assert response.status_code == 201
    body = response.json()
    assert body["institution_code"] == "INST-00001"
    assert body["name"] == "Alpha   Synthetic College"
    assert body["status"] == "active"
    assert body["created_at"].endswith("Z") or body["created_at"].endswith("+00:00")
    assert "id" not in body and "name_normalized" not in body and "seed_key" not in body
    assert response.headers["X-Request-ID"]


def test_codes_are_generated_sequentially_and_unique(client: TestClient) -> None:
    codes = [client.post(BASE, json=institution_payload(name=f"Synthetic College {i}")).json()["institution_code"]
             for i in range(3)]
    assert codes == ["INST-00001", "INST-00002", "INST-00003"]


def test_client_cannot_set_code_id_or_timestamps(client: TestClient) -> None:
    for extra in ({"institution_code": "HACK-1"}, {"id": "x"}, {"created_at": "2020-01-01T00:00:00Z"},
                  {"status": "inactive"}):
        response = client.post(BASE, json=institution_payload(**extra))
        assert response.status_code == 422, extra
        assert response.json()["error"]["code"] == "validation_error"


def test_duplicate_institution_code_rejected_by_database(client: TestClient, app) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    from app.models import Institution

    first = client.post(BASE, json=institution_payload()).json()
    with app.state.session_factory() as session:
        session.add(Institution(institution_code=first["institution_code"], name="Dup", name_normalized="dup",
                                institution_type="government", state="X1", district="Y1", address="Some addr",
                                trust_name="Trust", property_identifier="P-1"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_data_rejected(client: TestClient) -> None:
    cases = [
        institution_payload(name="ab"),
        institution_payload(institution_type="university_of_everything"),
        institution_payload(state=""),
        {k: v for k, v in institution_payload().items() if k != "address"},
    ]
    for payload in cases:
        response = client.post(BASE, json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["details"]


def test_list_pagination_and_ordering(client: TestClient) -> None:
    for name in ["Charlie Synthetic", "Alpha Synthetic", "Bravo Synthetic", "Delta Synthetic", "Echo Synthetic"]:
        client.post(BASE, json=institution_payload(name=name))
    page1 = client.get(BASE, params={"page": 1, "page_size": 2}).json()
    page3 = client.get(BASE, params={"page": 3, "page_size": 2}).json()
    assert [i["name"] for i in page1["items"]] == ["Alpha Synthetic", "Bravo Synthetic"]
    assert (page1["total"], page1["page"], page1["page_size"], page1["total_pages"]) == (5, 1, 2, 3)
    assert [i["name"] for i in page3["items"]] == ["Echo Synthetic"]
    assert client.get(BASE, params={"page_size": 101}).status_code == 422
    assert client.get(BASE, params={"page": 0}).status_code == 422


def test_search_by_name_and_code(client: TestClient) -> None:
    client.post(BASE, json=institution_payload(name="Kaveri Synthetic College"))
    client.post(BASE, json=institution_payload(name="Ganga Synthetic Institute"))
    assert [i["name"] for i in client.get(BASE, params={"q": "KAVERI"}).json()["items"]] == ["Kaveri Synthetic College"]
    assert client.get(BASE, params={"q": "inst-00002"}).json()["items"][0]["name"] == "Ganga Synthetic Institute"
    # LIKE wildcards in user input are treated literally.
    assert client.get(BASE, params={"q": "%"}).json()["total"] == 0


def test_detail_and_not_found(client: TestClient, institution: dict) -> None:
    code = institution["institution_code"]
    assert client.get(f"{BASE}/{code}").json() == institution
    missing = client.get(f"{BASE}/INST-99999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert client.patch(f"{BASE}/INST-99999", json={"name": "Whatever"}).status_code == 404


def test_update_institution(client: TestClient, institution: dict) -> None:
    code = institution["institution_code"]
    response = client.patch(f"{BASE}/{code}", json={"name": "Renamed Synthetic College", "status": "inactive"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed Synthetic College"
    assert body["status"] == "inactive"
    assert body["institution_code"] == code
    assert body["updated_at"] >= institution["updated_at"]
    assert client.get(BASE, params={"q": "renamed"}).json()["total"] == 1


def test_update_rejects_immutable_fields_and_nulls(client: TestClient, institution: dict) -> None:
    code = institution["institution_code"]
    for body in ({"institution_code": "NEW-1"}, {"created_at": "2020-01-01T00:00:00Z"}, {"name": None}):
        response = client.patch(f"{BASE}/{code}", json=body)
        assert response.status_code == 422, body
    assert client.get(f"{BASE}/{code}").json() == institution
