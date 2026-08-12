from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from cinevoice.config import validate_config

_PROFILE_DESCRIPTIONS = {
    "natural": "Gentle cleanup that preserves the original vocal tone",
    "studio": "Balanced clarity, dynamics and delivery loudness",
    "deep-narration": "Controlled low mids and cinematic narration presence",
}


def profile_directory() -> Path:
    return Path(__file__).resolve().parent / "profiles"


def list_profiles() -> list[dict[str, str]]:
    return [
        {"id": profile_id, "name": profile_id.replace("-", " ").title(), "description": description}
        for profile_id, description in _PROFILE_DESCRIPTIONS.items()
    ]


def load_profile(profile_id: str) -> dict[str, Any]:
    if profile_id not in _PROFILE_DESCRIPTIONS:
        raise ValueError("Unknown enhancement profile")
    path = profile_directory() / f"{profile_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_config(data)
    return copy.deepcopy(data)
