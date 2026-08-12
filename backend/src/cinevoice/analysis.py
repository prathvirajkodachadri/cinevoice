from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
from scipy import signal

from .models import AudioBuffer, AudioMetrics

_EPSILON = 1e-15
_ANALYSIS_RATE = 48_000

# ITU-R BS.1770 K-weighting coefficients at 48 kHz.
_K_SHELF_B = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
_K_SHELF_A = np.array([1.0, -1.69065929318241, 0.73248077421585])
_K_HIGHPASS_B = np.array([1.0, -2.0, 1.0])
_K_HIGHPASS_A = np.array([1.0, -1.99004745483398, 0.99007225036621])


def _db(value: float) -> float:
    return 20.0 * math.log10(max(value, _EPSILON))


def _resample(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return samples
    ratio = Fraction(target_rate, source_rate).limit_denominator(10_000)
    return signal.resample_poly(samples, ratio.numerator, ratio.denominator, axis=0)


def _k_weight(samples_48k: np.ndarray) -> np.ndarray:
    weighted = signal.lfilter(_K_SHELF_B, _K_SHELF_A, samples_48k, axis=0)
    return signal.lfilter(_K_HIGHPASS_B, _K_HIGHPASS_A, weighted, axis=0)


def _block_energies(
    weighted: np.ndarray,
    block_frames: int,
    step_frames: int,
) -> np.ndarray:
    frames = weighted.shape[0]
    if frames < block_frames:
        padded = np.pad(weighted, ((0, block_frames - frames), (0, 0)))
        return np.array([float(np.sum(np.mean(np.square(padded), axis=0)))])

    starts = np.arange(0, frames - block_frames + 1, step_frames)
    energies = np.empty(starts.shape[0], dtype=np.float64)
    for index, start in enumerate(starts):
        block = weighted[start : start + block_frames]
        energies[index] = float(np.sum(np.mean(np.square(block), axis=0)))
    return energies


def _energy_to_lufs(energy: np.ndarray | float) -> np.ndarray | float:
    return -0.691 + 10.0 * np.log10(np.maximum(energy, _EPSILON))


def integrated_loudness(weighted_48k: np.ndarray) -> float | None:
    energies = _block_energies(weighted_48k, int(0.4 * _ANALYSIS_RATE), int(0.1 * _ANALYSIS_RATE))
    loudness = np.asarray(_energy_to_lufs(energies))
    absolute = energies[loudness >= -70.0]
    if absolute.size == 0:
        return None

    absolute_mean = float(np.mean(absolute))
    relative_threshold = float(_energy_to_lufs(absolute_mean)) - 10.0
    relative = absolute[np.asarray(_energy_to_lufs(absolute)) >= relative_threshold]
    if relative.size == 0:
        return None
    return float(_energy_to_lufs(float(np.mean(relative))))


def short_term_loudness(weighted_48k: np.ndarray) -> np.ndarray:
    energies = _block_energies(weighted_48k, 3 * _ANALYSIS_RATE, int(0.1 * _ANALYSIS_RATE))
    return np.asarray(_energy_to_lufs(energies))


def true_peak(samples: np.ndarray) -> float:
    oversampled = signal.resample_poly(samples, 4, 1, axis=0, window=("kaiser", 8.6))
    return float(np.max(np.abs(oversampled)))


def _noise_floor_proxy(samples: np.ndarray, sample_rate: int) -> float | None:
    block_frames = max(1, int(round(sample_rate * 0.05)))
    usable = samples.shape[0] // block_frames * block_frames
    if usable == 0:
        return None
    mono_energy = np.mean(np.square(samples[:usable]), axis=1)
    blocks = mono_energy.reshape(-1, block_frames)
    block_rms = np.sqrt(np.mean(blocks, axis=1) + _EPSILON)
    finite = block_rms[np.isfinite(block_rms) & (block_rms > _EPSILON)]
    if finite.size == 0:
        return None
    return _db(float(np.percentile(finite, 20.0)))


def analyze(audio: AudioBuffer) -> AudioMetrics:
    samples = audio.samples.astype(np.float64, copy=False)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples)) + _EPSILON))
    crest = _db(peak / max(rms, _EPSILON))

    analysis_samples = _resample(samples, audio.sample_rate, _ANALYSIS_RATE)
    weighted = _k_weight(analysis_samples)
    integrated = integrated_loudness(weighted)
    short_term = short_term_loudness(weighted)
    valid_short = short_term[np.isfinite(short_term) & (short_term >= -70.0)]

    short_max = float(np.max(valid_short)) if valid_short.size else None
    if valid_short.size >= 2:
        gate = (integrated - 20.0) if integrated is not None else -70.0
        gated_short = valid_short[valid_short >= max(-70.0, gate)]
        lra = (
            float(np.percentile(gated_short, 95.0) - np.percentile(gated_short, 10.0))
            if gated_short.size >= 2
            else None
        )
    else:
        lra = None

    return AudioMetrics(
        sample_rate_hz=audio.sample_rate,
        channels=audio.channels,
        duration_seconds=round(audio.duration_seconds, 6),
        integrated_lufs=round(integrated, 2) if integrated is not None else None,
        short_term_max_lufs=round(short_max, 2) if short_max is not None else None,
        loudness_range_lu=round(lra, 2) if lra is not None else None,
        sample_peak_dbfs=round(_db(peak), 2),
        true_peak_dbtp=round(_db(true_peak(samples)), 2),
        rms_dbfs=round(_db(rms), 2),
        crest_factor_db=round(crest, 2),
        noise_floor_proxy_dbfs=(
            round(value, 2)
            if (value := _noise_floor_proxy(samples, audio.sample_rate)) is not None
            else None
        ),
        dc_offset=[round(float(value), 9) for value in np.mean(samples, axis=0)],
    )
