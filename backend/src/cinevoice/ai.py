from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class AIEnhancementError(RuntimeError):
    """Raised when a required speech-enhancement stage cannot complete."""


@dataclass(slots=True)
class AIEnhancementResult:
    output_path: Path | None
    executable: str | None
    used: bool
    warning: str | None = None


def find_deepfilter() -> str | None:
    return shutil.which("deep-filter") or shutil.which("deepFilter")


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
            "DeepFilterNet executable was not found. Install deep-filter or DeepFilterNet "
            "and place it on PATH."
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
        command = [executable, "--output-dir", str(output_directory)]
        if compensate_delay:
            command.append("--compensate-delay")
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
