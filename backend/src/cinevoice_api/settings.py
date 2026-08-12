from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


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
        max_upload_mb = _bounded_int("CINEVOICE_MAX_UPLOAD_MB", 250, 1, 2048)
        return cls(
            data_dir=data_dir,
            frontend_dir=frontend_dir,
            max_upload_bytes=max_upload_mb * 1024 * 1024,
            max_duration_seconds=_bounded_int(
                "CINEVOICE_MAX_DURATION_SECONDS", 3600, 1, 86_400
            ),
            retention_hours=_bounded_int("CINEVOICE_RETENTION_HOURS", 24, 1, 720),
            max_concurrent_jobs=_bounded_int("CINEVOICE_MAX_CONCURRENT_JOBS", 2, 1, 32),
            require_ai=_bool_env("CINEVOICE_REQUIRE_AI", False),
        )
