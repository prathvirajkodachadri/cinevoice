from __future__ import annotations

from fastapi.testclient import TestClient

from cinevoice_api.main import app


def test_health_describes_capabilities() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert ".wav" in payload["accepted_extensions"]
    assert len(payload["profiles"]) == 3
    assert payload["privacy"]["automatic_deletion"] is True
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_rejects_unsupported_upload() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("notes.txt", b"not audio", "text/plain")},
            data={"profile": "studio", "remove_noise": "false"},
        )
    assert response.status_code == 415
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"


def test_rejects_empty_upload() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("empty.wav", b"", "audio/wav")},
            data={"profile": "studio", "remove_noise": "false"},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_spa_does_not_hide_unknown_api_routes() -> None:
    with TestClient(app) as client:
        response = client.get("/api/does-not-exist")
        api_root = client.get("/api")
    assert response.status_code == 404
    assert response.json()["detail"] == "API route not found"
    assert api_root.status_code == 404
    assert api_root.json()["detail"] == "API route not found"
