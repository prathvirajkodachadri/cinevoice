from __future__ import annotations

from pathlib import Path

from cinevoice_api.job_store import JobStore


def test_job_lifecycle(tmp_path: Path) -> None:
    store = JobStore(tmp_path, retention_hours=24)
    created = store.create(filename="unsafe ../ voice.wav", profile="studio", remove_noise=True)
    assert created["status"] == "queued"
    assert "/" not in created["original_filename"]

    updated = store.update(created["id"], status="processing", progress=30)
    assert updated["progress"] == 30
    assert store.get(created["id"])["status"] == "processing"

    store.delete(created["id"])
    assert not (tmp_path / created["id"]).exists()
