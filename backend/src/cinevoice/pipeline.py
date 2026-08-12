from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .ai import run_deepfilter
from .analysis import analyze
from .audio_io import read_audio, sha256_file, write_audio_atomic
from .dsp.dynamics import compress, deess_gain, limit_peak
from .dsp.filters import bell, high_pass, low_pass_split
from .dsp.saturation import warm_saturation
from .models import AudioBuffer, ProcessResult, StageResult


def _gain(samples: np.ndarray, gain_db: float) -> np.ndarray:
    return samples * (10.0 ** (gain_db / 20.0))


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".json", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def process_file(
    input_path: str | Path,
    output_path: str | Path,
    config: dict[str, Any],
    *,
    report_path: str | Path | None = None,
    denoise_override: str | None = None,
) -> ProcessResult:
    source_path = Path(input_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if source_path == destination:
        raise ValueError("Output must not overwrite the source recording")

    original = read_audio(source_path)
    before = analyze(original)
    warnings: list[str] = []
    stages: list[StageResult] = []

    if original.channels != 1:
        warnings.append(
            "Narration profile is optimized for mono; stereo input was retained unchanged."
        )

    ai_config = config.get("ai_denoise", {})
    ai_mode = denoise_override or str(ai_config.get("mode", "auto"))
    if original.sample_rate != 48_000 and ai_mode != "off":
        message = "DeepFilterNet stage requires a 48 kHz WAV in version 0.1."
        if ai_mode == "required":
            raise ValueError(message)
        warnings.append(message + " AI denoising was skipped.")
        ai_mode = "off"

    ai_result, ai_temporary = run_deepfilter(
        source_path,
        mode=ai_mode,
        compensate_delay=bool(ai_config.get("compensate_delay", True)),
        post_filter=bool(ai_config.get("post_filter", False)),
    )
    if ai_result.warning:
        warnings.append(ai_result.warning)
    if ai_result.used and ai_result.output_path is not None:
        working = read_audio(ai_result.output_path)
        if working.channels != original.channels:
            if ai_temporary is not None:
                ai_temporary.cleanup()
            raise RuntimeError("DeepFilterNet changed the channel count unexpectedly")
        stages.append(
            StageResult(
                "ai_denoise",
                True,
                {"engine": "DeepFilterNet", "executable": ai_result.executable},
            )
        )
    else:
        working = AudioBuffer(original.samples.copy(), original.sample_rate, original.source)
        stages.append(StageResult("ai_denoise", False))

    samples = working.samples
    sample_rate = working.sample_rate

    high_pass_config = config.get("high_pass", {})
    if high_pass_config.get("enabled", False):
        frequency = float(high_pass_config["frequency_hz"])
        order = int(high_pass_config.get("order", 4))
        samples = high_pass(samples, sample_rate, frequency, order)
        stages.append(
            StageResult(
                "high_pass",
                True,
                {"frequency_hz": frequency, "order": order},
            )
        )
    else:
        stages.append(StageResult("high_pass", False))

    applied_bands: list[dict[str, Any]] = []
    for band in config.get("eq_bands", []):
        frequency = float(band["frequency_hz"])
        if frequency >= sample_rate / 2:
            warnings.append(f"EQ band at {frequency:g} Hz was skipped because it exceeds Nyquist.")
            continue
        gain_db = float(band["gain_db"])
        q = float(band["q"])
        samples = bell(samples, sample_rate, frequency, gain_db, q)
        applied_bands.append(
            {
                "frequency_hz": frequency,
                "gain_db": gain_db,
                "q": q,
                "reason": band.get("reason", ""),
            }
        )
    stages.append(StageResult("equalizer", bool(applied_bands), {"bands": applied_bands}))

    compressor_config = config.get("compressor", {})
    if compressor_config.get("enabled", False):
        samples, details = compress(
            samples,
            sample_rate,
            ratio=float(compressor_config["ratio"]),
            attack_ms=float(compressor_config["attack_ms"]),
            release_ms=float(compressor_config["release_ms"]),
            knee_db=float(compressor_config["knee_db"]),
            target_reduction_db=float(compressor_config["target_gain_reduction_db"]),
            makeup_gain_db=float(compressor_config["makeup_gain_db"]),
        )
        stages.append(StageResult("compressor", True, details))
    else:
        stages.append(StageResult("compressor", False))

    saturation_config = config.get("saturation", {})
    if saturation_config.get("enabled", False):
        drive_db = float(saturation_config["drive_db"])
        mix = float(saturation_config["mix"])
        samples = warm_saturation(samples, drive_db, mix)
        stages.append(StageResult("saturation", True, {"drive_db": drive_db, "mix": mix}))
    else:
        stages.append(StageResult("saturation", False))

    deesser_config = config.get("deesser", {})
    if deesser_config.get("enabled", False):
        crossover = float(deesser_config["crossover_hz"])
        if crossover < sample_rate / 2:
            low, high = low_pass_split(samples, sample_rate, crossover)
            deesser_gain, details = deess_gain(
                high,
                sample_rate,
                attack_ms=float(deesser_config["attack_ms"]),
                release_ms=float(deesser_config["release_ms"]),
                target_reduction_db=float(deesser_config["target_gain_reduction_db"]),
                maximum_reduction_db=float(deesser_config["maximum_gain_reduction_db"]),
            )
            samples = low + high * deesser_gain[:, None]
            details["crossover_hz"] = crossover
            stages.append(StageResult("deesser", True, details))
        else:
            warnings.append("De-esser crossover exceeds Nyquist and was skipped.")
            stages.append(StageResult("deesser", False))
    else:
        stages.append(StageResult("deesser", False))

    interim = AudioBuffer(samples, sample_rate)
    interim_metrics = analyze(interim)
    target_lufs = float(config["target_lufs"])
    if interim_metrics.integrated_lufs is None:
        normalization_gain_db = 0.0
        warnings.append(
            "Loudness normalization was skipped because integrated loudness was undefined."
        )
    else:
        normalization_gain_db = target_lufs - interim_metrics.integrated_lufs
        normalization_gain_db = float(np.clip(normalization_gain_db, -18.0, 18.0))
        samples = _gain(samples, normalization_gain_db)
    stages.append(
        StageResult(
            "loudness_normalization",
            True,
            {"target_lufs": target_lufs, "applied_gain_db": normalization_gain_db},
        )
    )

    limiter_config = config.get("limiter", {})
    ceiling = float(config["true_peak_ceiling_dbtp"])
    if limiter_config.get("enabled", False):
        samples, limiter_details = limit_peak(
            samples,
            sample_rate,
            ceiling_dbfs=ceiling,
            lookahead_ms=float(limiter_config["lookahead_ms"]),
            release_ms=float(limiter_config["release_ms"]),
        )
        recommended = float(limiter_config["maximum_recommended_reduction_db"])
        stage_warnings: list[str] = []
        if limiter_details["maximum_gain_reduction_db"] > recommended:
            message = (
                "Limiter exceeded the recommended reduction; use event gain or additional "
                "leveling before mastering."
            )
            stage_warnings.append(message)
            warnings.append(message)
        stages.append(StageResult("limiter", True, limiter_details, stage_warnings))
    else:
        stages.append(StageResult("limiter", False))

    preliminary = analyze(AudioBuffer(samples, sample_rate))
    if preliminary.true_peak_dbtp > ceiling:
        safety_trim_db = ceiling - preliminary.true_peak_dbtp - 0.02
        samples = _gain(samples, safety_trim_db)
        stages.append(
            StageResult(
                "true_peak_safety_trim",
                True,
                {"applied_gain_db": safety_trim_db, "ceiling_dbtp": ceiling},
            )
        )

    final_audio = AudioBuffer(samples, sample_rate)
    written = write_audio_atomic(destination, final_audio, subtype="PCM_24")
    after = analyze(read_audio(written))

    if after.integrated_lufs is not None and abs(after.integrated_lufs - target_lufs) > 1.0:
        warnings.append(
            "Final loudness is more than 1 LU from target; manual level review is required."
        )
    if after.true_peak_dbtp > ceiling + 0.1:
        warnings.append("True-peak verification failed; do not publish this render.")

    result = ProcessResult(
        input_path=str(source_path),
        output_path=str(written),
        input_sha256=sha256_file(source_path),
        output_sha256=sha256_file(written),
        preset_name=str(config["name"]),
        before=before,
        after=after,
        stages=stages,
        warnings=warnings,
    )

    if report_path is not None:
        _write_json_atomic(Path(report_path).expanduser().resolve(), result.to_dict())

    if ai_temporary is not None:
        ai_temporary.cleanup()
    return result
