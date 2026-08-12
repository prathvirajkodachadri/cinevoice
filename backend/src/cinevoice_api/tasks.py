from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from cinevoice.ai import find_deepfilter
from cinevoice.pipeline import process_file

from .job_store import JobStore
from .media import prepare_audio
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
            except Exception as exc:
                self.store.update(
                    job_id,
                    status="failed",
                    progress=100,
                    stage="Processing failed",
                    error=self._public_error(exc),
                )

    @staticmethod
    def _public_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:500]

    def _process(self, job_id: str, upload_path: Path) -> None:
        metadata = self.store.get(job_id)
        directory = self.store.directory(job_id)
        prepared_path = directory / "prepared.wav"
        output_path = directory / "enhanced.wav"
        report_path = directory / "report.json"

        self.store.update(job_id, status="processing", progress=10, stage="Preparing audio")
        prepare_audio(upload_path, prepared_path, self.settings.max_duration_seconds)

        remove_noise = bool(metadata["remove_noise"])
        if remove_noise and find_deepfilter() is None:
            raise RuntimeError(
                "The AI denoising model is not installed on this server. "
                "Install DeepFilterNet or turn off Remove noise."
            )
        if self.settings.require_ai and not remove_noise:
            raise RuntimeError("This deployment requires AI denoising for every job")

        self.store.update(
            job_id,
            progress=30,
            stage="AI noise cleanup" if remove_noise else "Voice enhancement",
        )
        config = load_profile(str(metadata["profile"]))
        result = process_file(
            prepared_path,
            output_path,
            config,
            report_path=report_path,
            denoise_override="required" if remove_noise else "off",
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
