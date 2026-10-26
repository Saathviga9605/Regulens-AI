from fastapi.testclient import TestClient


def test_system_info_returns_safe_metadata(client: TestClient, settings) -> None:
    response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "app_name",
        "app_version",
        "api_version",
        "environment",
        "demo_mode",
        "database_backend",
        "implemented_capabilities",
        "planned_capabilities",
        "ai_capabilities",
    }
    caps = body["ai_capabilities"]
    assert caps["ocr"]["engine"] == "none" and caps["ocr"]["available"] is False  # tests run with OCR disabled
    assert caps["local_text_model"]["configured"] is False and caps["local_vision_model"]["configured"] is False
    assert ":\\" not in response.text and "tesseract.exe" not in response.text  # no executable paths
    assert body["environment"] == "test"
    assert body["database_backend"] == "sqlite"
    assert body["planned_capabilities"]

    text = response.text.lower()
    assert settings.database_url.lower() not in text
    assert str(settings.sqlite_path).lower() not in text
    for forbidden in ("secret", "password", "token", "sqlite:///"):
        assert forbidden not in text


def test_capability_text_matches_implementation(client: TestClient) -> None:
    body = client.get("/api/v1/system/info").json()
    implemented = " ".join(body["implemented_capabilities"]).lower()
    planned = " ".join(body["planned_capabilities"]).lower()
    # built features are no longer advertised as planned
    for done in ("upload", "ocr", "extraction", "audit", "report"):
        assert done in implemented and done not in planned
    # no overclaiming: issuer checks are simulated or manual, APH rules are not approved or fully verified
    assert "simulated" in implemented and "not_connected" in implemented
    assert "live issuer verification" in planned and "live" not in implemented
    assert "partially verified" in implemented and "formal approval pending" in implemented
    assert "formally approved" not in implemented and "fully verified" not in implemented
    assert "synthetic" in planned  # real-photo evaluation not done
    assert "connection status" not in implemented  # removed from the dashboard in D11
