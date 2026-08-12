from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a processing profile is unsafe or malformed."""


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Unable to load preset {config_path}: {exc}") from exc
    validate_config(data)
    return data


def validate_config(data: dict[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise ConfigError("Only preset schema_version 1 is supported")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise ConfigError("Preset name is required")

    target = float(data.get("target_lufs", -14.0))
    if not -30.0 <= target <= -8.0:
        raise ConfigError("target_lufs must be between -30 and -8 LUFS")

    ceiling = float(data.get("true_peak_ceiling_dbtp", -1.0))
    if not -6.0 <= ceiling <= -0.1:
        raise ConfigError("true_peak_ceiling_dbtp must be between -6 and -0.1 dBTP")

    high_pass = data.get("high_pass", {})
    if high_pass.get("enabled", False):
        frequency = float(high_pass.get("frequency_hz", 0.0))
        if not 15.0 <= frequency <= 150.0:
            raise ConfigError("Voice high-pass frequency must be between 15 and 150 Hz")
        if int(high_pass.get("order", 4)) not in {1, 2, 3, 4, 6, 8}:
            raise ConfigError("Unsupported high-pass order")

    bands = data.get("eq_bands", [])
    if len(bands) > 8:
        raise ConfigError("A preset may contain no more than eight EQ bands")
    for index, band in enumerate(bands, start=1):
        if band.get("type") != "bell":
            raise ConfigError(f"EQ band {index}: only bell filters are supported")
        gain = float(band.get("gain_db", 0.0))
        q = float(band.get("q", 0.0))
        frequency = float(band.get("frequency_hz", 0.0))
        if not -6.0 <= gain <= 4.0:
            raise ConfigError(f"EQ band {index}: gain exceeds conservative safety limits")
        if not 0.2 <= q <= 12.0:
            raise ConfigError(f"EQ band {index}: Q is outside the supported range")
        if not 20.0 <= frequency <= 22_000.0:
            raise ConfigError(f"EQ band {index}: invalid frequency")

    compressor = data.get("compressor", {})
    if compressor.get("enabled", False):
        ratio = float(compressor.get("ratio", 0.0))
        target_gr = float(compressor.get("target_gain_reduction_db", 0.0))
        if not 1.0 < ratio <= 10.0:
            raise ConfigError("Compressor ratio must be greater than 1 and no more than 10")
        if not 0.0 <= target_gr <= 8.0:
            raise ConfigError("Compressor target reduction must be between 0 and 8 dB")

    saturation = data.get("saturation", {})
    if saturation.get("enabled", False):
        mix = float(saturation.get("mix", 0.0))
        drive = float(saturation.get("drive_db", 0.0))
        if not 0.0 <= mix <= 0.5:
            raise ConfigError("Saturation mix must be between 0 and 0.5")
        if not 0.0 <= drive <= 6.0:
            raise ConfigError("Saturation drive must be between 0 and 6 dB")
