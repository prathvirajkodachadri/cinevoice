from __future__ import annotations

import math

import numpy as np
from scipy import signal


def _filter_sos(samples: np.ndarray, sos: np.ndarray) -> np.ndarray:
    output = np.empty_like(samples, dtype=np.float64)
    zi_template = signal.sosfilt_zi(sos)
    for channel in range(samples.shape[1]):
        zi = zi_template * samples[0, channel]
        output[:, channel], _ = signal.sosfilt(sos, samples[:, channel], zi=zi)
    return output


def high_pass(
    samples: np.ndarray,
    sample_rate: int,
    frequency_hz: float,
    order: int = 4,
) -> np.ndarray:
    if not 0.0 < frequency_hz < sample_rate / 2:
        raise ValueError("High-pass frequency must be below Nyquist")
    sos = signal.butter(order, frequency_hz, btype="highpass", fs=sample_rate, output="sos")
    return _filter_sos(samples, sos)


def bell_sos(
    sample_rate: int,
    frequency_hz: float,
    gain_db: float,
    q: float,
) -> np.ndarray:
    if not 0.0 < frequency_hz < sample_rate / 2:
        raise ValueError("Bell frequency must be below Nyquist")
    if q <= 0.0:
        raise ValueError("Q must be positive")

    amplitude = 10.0 ** (gain_db / 40.0)
    omega = 2.0 * math.pi * frequency_hz / sample_rate
    alpha = math.sin(omega) / (2.0 * q)
    cosine = math.cos(omega)

    b0 = 1.0 + alpha * amplitude
    b1 = -2.0 * cosine
    b2 = 1.0 - alpha * amplitude
    a0 = 1.0 + alpha / amplitude
    a1 = -2.0 * cosine
    a2 = 1.0 - alpha / amplitude

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def bell(
    samples: np.ndarray,
    sample_rate: int,
    frequency_hz: float,
    gain_db: float,
    q: float,
) -> np.ndarray:
    return _filter_sos(samples, bell_sos(sample_rate, frequency_hz, gain_db, q))


def low_pass_split(
    samples: np.ndarray,
    sample_rate: int,
    frequency_hz: float,
    order: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    sos = signal.butter(order, frequency_hz, btype="lowpass", fs=sample_rate, output="sos")
    low = _filter_sos(samples, sos)
    high = samples - low
    return low, high
