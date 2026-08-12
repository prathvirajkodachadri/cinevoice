from __future__ import annotations

from pathlib import Path
from uuid import uuid1

import pytest

from cinevoice_api.job_store import JobNotFoundError, JobStore


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


def test_rejects_noncanonical_and_non_v4_ids(tmp_path: Path) -> None:
    store = JobStore(tmp_path, retention_hours=24)
    created = store.create(filename="voice.wav", profile="studio", remove_noise=False)

    with pytest.raises(JobNotFoundError):
        store.get(created["id"].upper())
    with pytest.raises(JobNotFoundError):
        store.get(str(uuid1()))


def test_recovers_interrupted_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path, retention_hours=24)
    queued = store.create(filename="voice.wav", profile="natural", remove_noise=False)
    complete = store.create(filename="done.wav", profile="studio", remove_noise=False)
    store.update(complete["id"], status="completed", progress=100)

    assert store.recover_interrupted() == 1
    recovered = store.get(queued["id"])
    assert recovered["status"] == "failed"
    assert "restarted" in recovered["error"]
    assert store.get(complete["id"])["status"] == "completed"
