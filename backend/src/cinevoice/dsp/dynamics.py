from __future__ import annotations

import math
from collections import deque

import numpy as np

_EPSILON = 1e-12


def _time_coefficient(milliseconds: float, sample_rate: int) -> float:
    if milliseconds <= 0.0:
        return 0.0
    return math.exp(-1.0 / (0.001 * milliseconds * sample_rate))


def envelope_follower(
    detector: np.ndarray,
    sample_rate: int,
    attack_ms: float,
    release_ms: float,
) -> np.ndarray:
    attack = _time_coefficient(attack_ms, sample_rate)
    release = _time_coefficient(release_ms, sample_rate)
    envelope = np.empty(detector.shape[0], dtype=np.float64)
    current = 0.0
    for index, value in enumerate(detector):
        coefficient = attack if value > current else release
        current = coefficient * current + (1.0 - coefficient) * float(value)
        envelope[index] = current
    return envelope


def _gain_reduction_db(
    level_db: np.ndarray,
    threshold_db: float,
    ratio: float,
    knee_db: float,
) -> np.ndarray:
    over = level_db - threshold_db
    if knee_db <= 0.0:
        return np.where(over > 0.0, over * (1.0 - 1.0 / ratio), 0.0)

    half_knee = knee_db / 2.0
    reduction = np.zeros_like(level_db)
    above = over >= half_knee
    within = (over > -half_knee) & (over < half_knee)
    reduction[above] = over[above] * (1.0 - 1.0 / ratio)
    reduction[within] = (1.0 - 1.0 / ratio) * np.square(over[within] + half_knee) / (2.0 * knee_db)
    return reduction


def _auto_threshold(
    level_db: np.ndarray,
    ratio: float,
    knee_db: float,
    target_reduction_db: float,
) -> float:
    active = level_db[np.isfinite(level_db) & (level_db > -100.0)]
    if active.size == 0:
        return -18.0
    representative_peak = float(np.percentile(active, 95.0))
    low, high = -80.0, representative_peak + 6.0
    for _ in range(50):
        midpoint = (low + high) / 2.0
        reduction = _gain_reduction_db(np.array([representative_peak]), midpoint, ratio, knee_db)[0]
        if reduction > target_reduction_db:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def compress(
    samples: np.ndarray,
    sample_rate: int,
    *,
    ratio: float,
    attack_ms: float,
    release_ms: float,
    knee_db: float,
    target_reduction_db: float,
    makeup_gain_db: float,
) -> tuple[np.ndarray, dict[str, float]]:
    detector = np.sqrt(np.mean(np.square(samples), axis=1) + _EPSILON)
    envelope = envelope_follower(detector, sample_rate, attack_ms, release_ms)
    level_db = 20.0 * np.log10(np.maximum(envelope, _EPSILON))
    threshold_db = _auto_threshold(level_db, ratio, knee_db, target_reduction_db)
    reduction_db = _gain_reduction_db(level_db, threshold_db, ratio, knee_db)
    gain = np.power(10.0, (-reduction_db + makeup_gain_db) / 20.0)
    output = samples * gain[:, None]
    return output, {
        "threshold_dbfs": float(threshold_db),
        "maximum_gain_reduction_db": float(np.max(reduction_db)),
        "p95_gain_reduction_db": float(np.percentile(reduction_db, 95.0)),
        "makeup_gain_db": float(makeup_gain_db),
    }


def deess_gain(
    high_band: np.ndarray,
    sample_rate: int,
    *,
    attack_ms: float,
    release_ms: float,
    target_reduction_db: float,
    maximum_reduction_db: float,
) -> tuple[np.ndarray, dict[str, float]]:
    detector = np.sqrt(np.mean(np.square(high_band), axis=1) + _EPSILON)
    envelope = envelope_follower(detector, sample_rate, attack_ms, release_ms)
    level_db = 20.0 * np.log10(np.maximum(envelope, _EPSILON))
    active = level_db[level_db > -100.0]
    threshold = float(np.percentile(active, 90.0) - target_reduction_db) if active.size else -30.0
    reduction = np.clip(level_db - threshold, 0.0, maximum_reduction_db)
    gain = np.power(10.0, -reduction / 20.0)
    return gain, {
        "threshold_dbfs": threshold,
        "maximum_gain_reduction_db": float(np.max(reduction)),
        "p95_gain_reduction_db": float(np.percentile(reduction, 95.0)),
    }


def _future_peak(values: np.ndarray, lookahead: int) -> np.ndarray:
    if lookahead <= 1:
        return values.copy()
    result = np.empty_like(values)
    candidates: deque[int] = deque()
    length = values.shape[0]

    for index in range(length - 1, -1, -1):
        while candidates and candidates[0] > index + lookahead:
            candidates.popleft()
        while candidates and values[candidates[-1]] <= values[index]:
            candidates.pop()
        candidates.append(index)
        result[index] = values[candidates[0]]
    return result


def limit_peak(
    samples: np.ndarray,
    sample_rate: int,
    *,
    ceiling_dbfs: float,
    lookahead_ms: float,
    release_ms: float,
) -> tuple[np.ndarray, dict[str, float]]:
    ceiling = 10.0 ** (ceiling_dbfs / 20.0)
    peak = np.max(np.abs(samples), axis=1)
    lookahead = max(1, int(round(sample_rate * lookahead_ms / 1000.0)))
    anticipated = _future_peak(peak, lookahead)
    target_gain = np.minimum(1.0, ceiling / np.maximum(anticipated, _EPSILON))

    release = _time_coefficient(release_ms, sample_rate)
    gain = np.empty_like(target_gain)
    current = 1.0
    for index, target in enumerate(target_gain):
        if target < current:
            current = float(target)
        else:
            current = release * current + (1.0 - release) * float(target)
        gain[index] = current

    reduction_db = -20.0 * np.log10(np.maximum(gain, _EPSILON))
    return samples * gain[:, None], {
        "maximum_gain_reduction_db": float(np.max(reduction_db)),
        "p95_gain_reduction_db": float(np.percentile(reduction_db, 95.0)),
        "lookahead_ms": float(lookahead_ms),
        "release_ms": float(release_ms),
    }
