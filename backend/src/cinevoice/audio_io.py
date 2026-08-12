from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .models import AudioBuffer


class AudioIOError(RuntimeError):
    """Raised when an audio file cannot be read or written safely."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_audio(path: str | Path) -> AudioBuffer:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise AudioIOError(f"Input file does not exist: {source}")
    try:
        samples, sample_rate = sf.read(source, dtype="float64", always_2d=True)
    except (RuntimeError, OSError) as exc:
        raise AudioIOError(f"Unable to read {source}: {exc}") from exc

    if samples.shape[1] > 8:
        raise AudioIOError("More than eight channels are not supported in version 0.1")
    peak = float(np.max(np.abs(samples)))
    if peak > 1.5:
        raise AudioIOError(
            "Input exceeds safe normalized floating-point range; inspect the source conversion"
        )
    return AudioBuffer(samples=samples, sample_rate=int(sample_rate), source=source)


def write_audio_atomic(
    path: str | Path,
    audio: AudioBuffer,
    *,
    subtype: str = "PCM_24",
) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix or ".wav"

    if suffix.lower() != ".wav":
        raise AudioIOError("Version 0.1 writes WAV only to keep delivery deterministic")

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.", suffix=suffix, dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        sf.write(temporary, audio.samples, audio.sample_rate, subtype=subtype, format="WAV")
        os.replace(temporary, destination)
    except (RuntimeError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise AudioIOError(f"Unable to write {destination}: {exc}") from exc
    return destination
