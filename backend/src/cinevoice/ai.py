from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class AIEnhancementError(RuntimeError):
    """Raised when a required speech-enhancement stage cannot complete."""


@dataclass(slots=True)
class AIEnhancementResult:
    output_path: Path | None
    executable: str | None
    used: bool
    warning: str | None = None


@lru_cache(maxsize=1)
def find_deepfilter() -> str | None:
    """Return a runnable DeepFilterNet CLI, including an explicitly configured path."""
    executable_names = ("deep-filter", "deepFilter", "deep-filter.exe", "deepFilter.exe")
    candidates: list[str] = []
    if configured := os.getenv("CINEVOICE_DEEPFILTER_PATH"):
        candidates.append(str(Path(configured).expanduser().resolve()))

    # Console scripts installed into the active virtual environment are discoverable even
    # when its bin directory was not prepended to the service manager's PATH.
    python_bin = Path(sys.executable).resolve().parent
    candidates.extend(str(python_bin / name) for name in executable_names)
    candidates.extend(
        executable
        for name in executable_names
        if (executable := shutil.which(name)) is not None
    )

    for executable in dict.fromkeys(candidates):
        path = Path(executable)
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        try:
            probe = subprocess.run(
                [executable, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return executable
    return None


def run_deepfilter(
    input_path: str | Path,
    *,
    mode: str,
    compensate_delay: bool,
    post_filter: bool,
) -> tuple[AIEnhancementResult, tempfile.TemporaryDirectory[str] | None]:
    if mode == "off":
        return AIEnhancementResult(None, None, False), None
    if mode not in {"auto", "required"}:
        raise AIEnhancementError(f"Unknown DeepFilterNet mode: {mode}")

    executable = find_deepfilter()
    if executable is None:
        message = (
            "A working DeepFilterNet executable was not found. Install deep-filter or "
            "DeepFilterNet, place it on PATH, or set CINEVOICE_DEEPFILTER_PATH."
        )
        if mode == "required":
            raise AIEnhancementError(message)
        return AIEnhancementResult(None, None, False, message), None

    temporary = tempfile.TemporaryDirectory(prefix="cinevoice-deepfilter-")
    output_directory = Path(temporary.name)
    executable_name = Path(executable).name.lower()

    if executable_name == "deep-filter" or executable_name == "deep-filter.exe":
        command = [executable, "-o", str(output_directory)]
        if compensate_delay:
            command.append("-D")
        if post_filter:
            command.append("--pf")
        command.append(str(Path(input_path).resolve()))
    else:
        # The Python DeepFilterNet CLI compensates delay by default and only exposes
        # the inverse flag. Passing the standalone binary's compensation option here
        # makes every Python-package installation fail with an unknown argument.
        command = [executable, "--output-dir", str(output_directory)]
        if not compensate_delay:
            command.append("--no-delay-compensation")
        if post_filter:
            command.append("--pf")
        command.append(str(Path(input_path).resolve()))

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,
        )
    except subprocess.TimeoutExpired as exc:
        temporary.cleanup()
        message = "DeepFilterNet timed out while cleaning the recording"
        if mode == "required":
            raise AIEnhancementError(message) from exc
        return AIEnhancementResult(None, executable, False, message), None
    except OSError as exc:
        temporary.cleanup()
        message = "DeepFilterNet could not be started"
        if mode == "required":
            raise AIEnhancementError(message) from exc
        return AIEnhancementResult(None, executable, False, message), None

    if completed.returncode != 0:
        temporary.cleanup()
        details = completed.stderr.strip() or completed.stdout.strip() or "Unknown error"
        # Keep untrusted decoder/model output bounded before it reaches job metadata.
        message = f"DeepFilterNet failed: {details[:400]}"
        if mode == "required":
            raise AIEnhancementError(message)
        return AIEnhancementResult(None, executable, False, message), None

    candidates = sorted(output_directory.rglob("*.wav"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        temporary.cleanup()
        message = "DeepFilterNet completed without producing a WAV file"
        if mode == "required":
            raise AIEnhancementError(message)
        return AIEnhancementResult(None, executable, False, message), None

    return AIEnhancementResult(candidates[-1], executable, True), temporary
