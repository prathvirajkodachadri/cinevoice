from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class JobNotFoundError(KeyError):
    pass


class JobStore:
    def __init__(self, root: Path, retention_hours: int) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.retention = timedelta(hours=retention_hours)
        self._lock = threading.RLock()

    @staticmethod
    def safe_filename(filename: str | None) -> str:
        candidate = Path(filename or "upload.wav").name
        cleaned = _SAFE_NAME.sub("-", candidate).strip(".-")
        return cleaned[:120] or "upload.wav"

    @staticmethod
    def validate_id(job_id: str) -> str:
        try:
            parsed = UUID(job_id, version=4)
        except ValueError as exc:
            raise JobNotFoundError(job_id) from exc
        return str(parsed)

    def directory(self, job_id: str) -> Path:
        valid = self.validate_id(job_id)
        directory = (self.root / valid).resolve()
        if self.root not in directory.parents:
            raise JobNotFoundError(job_id)
        return directory

    def create(self, *, filename: str, profile: str, remove_noise: bool) -> dict[str, Any]:
        with self._lock:
            job_id = str(uuid4())
            directory = self.root / job_id
            directory.mkdir(mode=0o700)
            now = datetime.now(UTC)
            metadata: dict[str, Any] = {
                "id": job_id,
                "status": "queued",
                "progress": 0,
                "stage": "Upload received",
                "profile": profile,
                "remove_noise": remove_noise,
                "original_filename": self.safe_filename(filename),
                "created_at": now.isoformat(),
                "expires_at": (now + self.retention).isoformat(),
                "error": None,
                "warnings": [],
                "metrics": None,
            }
            self._write(job_id, metadata)
            return metadata

    def _metadata_path(self, job_id: str) -> Path:
        return self.directory(job_id) / "job.json"

    def _write(self, job_id: str, metadata: dict[str, Any]) -> None:
        path = self._metadata_path(job_id)
        fd, temporary_name = tempfile.mkstemp(prefix=".job-", suffix=".json", dir=path.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            path = self._metadata_path(job_id)
            if not path.is_file():
                raise JobNotFoundError(job_id)
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise JobNotFoundError(job_id) from exc

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            metadata = self.get(job_id)
            metadata.update(changes)
            self._write(job_id, metadata)
            return metadata

    def delete(self, job_id: str) -> None:
        with self._lock:
            directory = self.directory(job_id)
            if not directory.is_dir():
                raise JobNotFoundError(job_id)
            shutil.rmtree(directory)

    def cleanup_expired(self) -> int:
        removed = 0
        now = datetime.now(UTC)
        with self._lock:
            for directory in self.root.iterdir():
                if not directory.is_dir():
                    continue
                try:
                    metadata = self.get(directory.name)
                    expires = datetime.fromisoformat(metadata["expires_at"])
                except (JobNotFoundError, KeyError, ValueError):
                    continue
                if expires <= now:
                    shutil.rmtree(directory, ignore_errors=True)
                    removed += 1
        return removed
