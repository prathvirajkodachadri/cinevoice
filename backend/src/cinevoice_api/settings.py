from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    frontend_dir: Path | None
    max_upload_bytes: int
    max_duration_seconds: int
    retention_hours: int
    max_concurrent_jobs: int
    require_ai: bool

    @classmethod
    def from_environment(cls) -> Settings:
        data_dir = Path(os.getenv("CINEVOICE_DATA_DIR", "./data/jobs")).resolve()
        frontend_value = os.getenv("CINEVOICE_FRONTEND_DIR", "./frontend/dist")
        frontend_dir = Path(frontend_value).resolve() if frontend_value else None
        return cls(
            data_dir=data_dir,
            frontend_dir=frontend_dir,
            max_upload_bytes=int(os.getenv("CINEVOICE_MAX_UPLOAD_MB", "250")) * 1024 * 1024,
            max_duration_seconds=int(os.getenv("CINEVOICE_MAX_DURATION_SECONDS", "3600")),
            retention_hours=int(os.getenv("CINEVOICE_RETENTION_HOURS", "24")),
            max_concurrent_jobs=max(1, int(os.getenv("CINEVOICE_MAX_CONCURRENT_JOBS", "2"))),
            require_ai=_bool_env("CINEVOICE_REQUIRE_AI", False),
        )
