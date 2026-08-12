from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from cinevoice.ai import AIEnhancementError, find_deepfilter
from cinevoice.audio_io import AudioIOError
from cinevoice.pipeline import process_file

from .job_store import JobNotFoundError, JobStore
from .media import MediaError, prepare_audio
from .profiles import load_profile
from .settings import Settings


class Processor:
    def __init__(self, settings: Settings, store: JobStore) -> None:
        self.settings = settings
        self.store = store
        self._slots = threading.BoundedSemaphore(settings.max_concurrent_jobs)

    def run(self, job_id: str, upload_path: Path) -> None:
        with self._slots:
            try:
                self._process(job_id, upload_path)
            except JobNotFoundError:
                # Immediate deletion is also cancellation. A progress write notices it and exits.
                return
            except Exception as exc:
                try:
                    self.store.update(
                        job_id,
                        status="failed",
                        progress=100,
                        stage="Processing failed",
                        error=self._public_error(exc),
                    )
                except JobNotFoundError:
                    return

    @staticmethod
    def _public_error(exc: Exception) -> str:
        if isinstance(exc, MediaError):
            return str(exc)[:500]
        if isinstance(exc, AIEnhancementError):
            return (
                "AI noise removal could not complete. Try again or turn off background-noise "
                "removal."
            )
        if isinstance(exc, AudioIOError):
            return "The recording could not be read safely. Try exporting it again."
        if isinstance(exc, ValueError):
            return f"The recording could not be processed: {str(exc)[:380]}"
        return "An unexpected processing error occurred. Please try again."

    def _progress(self, job_id: str, progress: int, stage: str) -> None:
        self.store.update(
            job_id,
            status="processing",
            progress=progress,
            stage=stage,
            error=None,
        )

    def _process(self, job_id: str, upload_path: Path) -> None:
        metadata = self.store.get(job_id)
        directory = self.store.directory(job_id)
        prepared_path = directory / "prepared.wav"
        output_path = directory / "enhanced.wav"
        report_path = directory / "report.json"

        self._progress(job_id, 10, "Validating recording")
        try:
            prepare_audio(upload_path, prepared_path, self.settings.max_duration_seconds)
            self._progress(job_id, 24, "Preparing enhancement")

            remove_noise = bool(metadata["remove_noise"])
            if remove_noise and find_deepfilter() is None:
                raise AIEnhancementError("DeepFilterNet is unavailable")
            if self.settings.require_ai and not remove_noise:
                raise ValueError("This deployment requires AI denoising for every job")

            config = load_profile(str(metadata["profile"]))
            result = process_file(
                prepared_path,
                output_path,
                config,
                report_path=report_path,
                denoise_override="required" if remove_noise else "off",
                progress_callback=lambda progress, stage: self._progress(
                    job_id, progress, stage
                ),
            )

            public_metrics: dict[str, Any] = {
                "before": result.before.to_dict(),
                "after": result.after.to_dict(),
            }
            self.store.update(
                job_id,
                status="completed",
                progress=100,
                stage="Ready to download",
                warnings=result.warnings,
                metrics=public_metrics,
                error=None,
            )
        finally:
            # The prepared PCM is an implementation detail and can be large; source/result suffice.
            prepared_path.unlink(missing_ok=True)
