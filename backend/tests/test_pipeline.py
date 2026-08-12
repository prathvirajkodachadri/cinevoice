from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from cinevoice.pipeline import process_file
from cinevoice_api.profiles import load_profile


def test_studio_pipeline_respects_true_peak(tmp_path: Path) -> None:
    sample_rate = 48_000
    time = np.arange(sample_rate * 4) / sample_rate
    samples = (0.05 * np.sin(2 * np.pi * 120 * time))[:, None]
    source = tmp_path / "source.wav"
    output = tmp_path / "enhanced.wav"
    sf.write(source, samples, sample_rate, subtype="PCM_24")

    progress: list[tuple[int, str]] = []
    report_path = tmp_path / "report.json"
    result = process_file(
        source,
        output,
        load_profile("studio"),
        report_path=report_path,
        denoise_override="off",
        progress_callback=lambda value, stage: progress.append((value, stage)),
    )
    assert output.is_file()
    assert result.after.true_peak_dbtp <= -0.85
    assert progress[0] == (30, "Analyzing source")
    assert progress[-1] == (95, "Writing studio master")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "input_path" not in report
    assert "output_path" not in report
    assert report["input_sha256"] == result.input_sha256
