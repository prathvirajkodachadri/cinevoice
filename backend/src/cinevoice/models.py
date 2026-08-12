from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(slots=True)
class AudioBuffer:
    samples: np.ndarray
    sample_rate: int
    source: Path | None = None

    def __post_init__(self) -> None:
        if self.samples.ndim != 2:
            raise ValueError("Audio samples must have shape (frames, channels)")
        if self.samples.shape[0] == 0 or self.samples.shape[1] == 0:
            raise ValueError("Audio is empty")
        if self.sample_rate < 8_000 or self.sample_rate > 384_000:
            raise ValueError(f"Unsupported sample rate: {self.sample_rate}")
        if not np.isfinite(self.samples).all():
            raise ValueError("Audio contains NaN or infinite samples")

    @property
    def frames(self) -> int:
        return int(self.samples.shape[0])

    @property
    def channels(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate


@dataclass(slots=True)
class AudioMetrics:
    sample_rate_hz: int
    channels: int
    duration_seconds: float
    integrated_lufs: float | None
    short_term_max_lufs: float | None
    loudness_range_lu: float | None
    sample_peak_dbfs: float
    true_peak_dbtp: float
    rms_dbfs: float
    crest_factor_db: float
    noise_floor_proxy_dbfs: float | None
    dc_offset: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StageResult:
    name: str
    enabled: bool
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProcessResult:
    input_path: str
    output_path: str
    input_sha256: str
    output_sha256: str
    preset_name: str
    before: AudioMetrics
    after: AudioMetrics
    stages: list[StageResult]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "preset_name": self.preset_name,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "stages": [asdict(stage) for stage in self.stages],
            "warnings": self.warnings,
        }
