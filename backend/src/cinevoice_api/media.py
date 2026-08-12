from __future__ import annotations

import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import soundfile as sf
from scipy import signal

from cinevoice.audio_io import read_audio, write_audio_atomic
from cinevoice.models import AudioBuffer

ACCEPTED_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aac"}
NATIVE_EXTENSIONS = {".wav", ".flac", ".ogg"}
FFMPEG_EXTENSIONS = ACCEPTED_EXTENSIONS - NATIVE_EXTENSIONS


class MediaError(RuntimeError):
    """Raised when an uploaded media file cannot be prepared safely."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def available_extensions() -> set[str]:
    return ACCEPTED_EXTENSIONS if ffmpeg_available() else NATIVE_EXTENSIONS


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
    # DeepFilterNet's standalone reader expects 16-bit PCM WAV input.
    write_audio_atomic(destination, prepared, subtype="PCM_16")
    return prepared


def _duration_from_ffprobe(path: Path) -> float | None:
    executable = shutil.which("ffprobe")
    if executable is None:
        return None
    try:
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
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        value = float(completed.stdout.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0.0 else None


def _native_duration(path: Path) -> float | None:
    try:
        info = sf.info(path)
    except (RuntimeError, OSError, ValueError):
        return None
    if info.samplerate <= 0:
        return None
    return info.frames / info.samplerate


def _decode_with_ffmpeg(
    source: Path,
    destination: Path,
    max_duration_seconds: int,
) -> AudioBuffer:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise MediaError("This audio format requires FFmpeg, which is unavailable on the server.")

    duration = _duration_from_ffprobe(source)
    if duration is not None and duration > max_duration_seconds:
        raise MediaError("Audio duration exceeds the configured limit.")

    # A hard output bound protects the worker when container metadata is absent or false.
    decode_limit = max_duration_seconds + 1
    destination.unlink(missing_ok=True)
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                "-t",
                str(decode_limit),
                "-y",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=max(120, min(900, max_duration_seconds * 2)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        destination.unlink(missing_ok=True)
        raise MediaError("Audio decoding timed out. Try a shorter recording.") from exc
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise MediaError("The server could not start its audio decoder.") from exc

    if completed.returncode != 0:
        destination.unlink(missing_ok=True)
        raise MediaError(
            "The audio file could not be decoded. Check that it is a valid, supported recording."
        )

    try:
        prepared = read_audio(destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise MediaError("The decoded recording was not valid audio.") from exc
    if prepared.duration_seconds > max_duration_seconds:
        destination.unlink(missing_ok=True)
        raise MediaError("Audio duration exceeds the configured limit.")
    return prepared


def prepare_audio(source: Path, destination: Path, max_duration_seconds: int) -> AudioBuffer:
    extension = source.suffix.lower()
    if extension not in ACCEPTED_EXTENSIONS:
        raise MediaError("Unsupported audio format.")

    if extension in NATIVE_EXTENSIONS:
        duration = _native_duration(source)
        if duration is not None and duration > max_duration_seconds:
            raise MediaError("Audio duration exceeds the configured limit.")
        try:
            prepared = _resample_to_48k(source, destination)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise MediaError(
                "The audio file could not be decoded. "
                "Check that it is a valid, supported recording."
            ) from exc
        if prepared.duration_seconds > max_duration_seconds:
            destination.unlink(missing_ok=True)
            raise MediaError("Audio duration exceeds the configured limit.")
        return prepared

    return _decode_with_ffmpeg(source, destination, max_duration_seconds)
