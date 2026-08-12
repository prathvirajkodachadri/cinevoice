from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "processing", "completed", "failed"]


class JobPublic(BaseModel):
    id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    stage: str
    profile: str
    remove_noise: bool
    original_filename: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    source_bytes: int | None = Field(default=None, ge=0)
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None
    links: dict[str, str]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    ai_denoise_available: bool
    ai_denoise_required: bool
    ffmpeg_available: bool
    accepted_extensions: list[str]
    profiles: list[dict[str, str]]
    limits: dict[str, int]
    privacy: dict[str, Any]
