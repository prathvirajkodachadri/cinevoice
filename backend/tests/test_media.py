from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from cinevoice_api.media import prepare_audio


def test_prepare_resamples_wav_to_48k(tmp_path: Path) -> None:
    sample_rate = 44_100
    time = np.arange(sample_rate) / sample_rate
    samples = 0.1 * np.sin(2 * np.pi * 440 * time)
    source = tmp_path / "source.wav"
    destination = tmp_path / "prepared.wav"
    sf.write(source, samples, sample_rate)

    prepared = prepare_audio(source, destination, max_duration_seconds=10)
    assert prepared.sample_rate == 48_000
    assert prepared.channels == 1
    assert destination.is_file()
