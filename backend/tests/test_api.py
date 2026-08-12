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


def test_rejects_unsupported_upload() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("notes.txt", b"not audio", "text/plain")},
            data={"profile": "studio", "remove_noise": "false"},
        )
    assert response.status_code == 415
