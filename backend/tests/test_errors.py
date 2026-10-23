from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_unexpected_exception_hides_internal_details(app: FastAPI) -> None:
    secret_path = "C:\\internal\\secret\\module.py"

    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError(f"failure reading {secret_path}")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["message"] == "An unexpected error occurred."
    assert error["request_id"]
    for leaked in ("Traceback", "RuntimeError", secret_path, "module.py", ".py\""):
        assert leaked not in response.text


def test_unknown_route_uses_consistent_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_method_not_allowed_uses_consistent_error_shape(client: TestClient) -> None:
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
