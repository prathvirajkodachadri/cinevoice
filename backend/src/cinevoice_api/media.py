from __future__ import annotations

import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from scipy import signal

from cinevoice.audio_io import read_audio, write_audio_atomic
from cinevoice.models import AudioBuffer

ACCEPTED_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac"}
NATIVE_EXTENSIONS = {".wav", ".flac", ".ogg"}


class MediaError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _resample_to_48k(source: Path, destination: Path) -> AudioBuffer:
    audio = read_audio(source)
    if audio.sample_rate == 48_000:
        prepared = AudioBuffer(audio.samples.copy(), 48_000, source)
    else:
        ratio = Fraction(48_000, audio.sample_rate).limit_denominator(10_000)
        samples = signal.resample_poly(
            audio.samples, ratio.numerator, ratio.denominator, axis=0, window=("kaiser", 8.6)
        )
        prepared = AudioBuffer(samples, 48_000, source)
    # DeepFilterNet's standalone 0.5.6 reader expects 16-bit PCM WAV input.
    write_audio_atomic(destination, prepared, subtype="PCM_16")
    return prepared


def _duration_from_ffprobe(path: Path) -> float | None:
    executable = shutil.which("ffprobe")
    if executable is None:
        return None
    completed = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        value = float(completed.stdout.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def prepare_audio(source: Path, destination: Path, max_duration_seconds: int) -> AudioBuffer:
    extension = source.suffix.lower()
    if extension not in ACCEPTED_EXTENSIONS:
        raise MediaError("Unsupported audio format")

    if extension in NATIVE_EXTENSIONS:
        try:
            prepared = _resample_to_48k(source, destination)
        except Exception as exc:
            raise MediaError(f"Audio decoder rejected the file: {exc}") from exc
        if prepared.duration_seconds > max_duration_seconds:
            raise MediaError("Audio duration exceeds the configured limit")
        return prepared

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise MediaError("MP3, M4A and AAC require FFmpeg on the server")

    duration = _duration_from_ffprobe(source)
    if duration is not None and duration > max_duration_seconds:
        raise MediaError("Audio duration exceeds the configured limit")

    completed = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vn",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            "-y",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        raise MediaError(completed.stderr.strip() or "FFmpeg could not decode the upload")

    prepared = read_audio(destination)
    if prepared.duration_seconds > max_duration_seconds:
        destination.unlink(missing_ok=True)
        raise MediaError("Audio duration exceeds the configured limit")
    return prepared
