from __future__ import annotations

import numpy as np


def warm_saturation(samples: np.ndarray, drive_db: float, mix: float) -> np.ndarray:
    if not 0.0 <= mix <= 1.0:
        raise ValueError("Saturation mix must be between 0 and 1")
    drive = 10.0 ** (drive_db / 20.0)
    normalization = np.tanh(drive)
    if normalization == 0.0:
        return samples.copy()
    wet = np.tanh(samples * drive) / normalization
    return samples * (1.0 - mix) + wet * mix
