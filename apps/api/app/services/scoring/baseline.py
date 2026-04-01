"""Adaptive baseline: chapter/narrator statistics for z-score normalization."""

from __future__ import annotations

import json
from typing import Any, Sequence

MIN_SEGMENTS_FOR_STABLE_BASELINE = 30
BLEND_RATIO_UNSTABLE = 0.5


def build_chapter_baseline(
    issue_records: list[dict[str, Any]],
    prosody_map: list[dict[str, Any]],
    audio_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build adaptive baseline statistics for a chapter."""
    speech_rates = []
    f0_means = []
    f0_stds = []
    rms_values = []
    centroids = []
    pauses = []

    for issue in issue_records:
        try:
            prosody = json.loads(issue.get("prosody_features_json", "{}") or "{}")
        except (json.JSONDecodeError, TypeError):
            prosody = {}
        try:
            audio = json.loads(issue.get("audio_features_json", "{}") or "{}")
        except (json.JSONDecodeError, TypeError):
            audio = {}

        rate = prosody.get("speech_rate_wps", 0.0)
        if rate > 0:
            speech_rates.append(rate)

        f0 = prosody.get("f0_mean_hz")
        if f0 is not None and f0 > 0:
            f0_means.append(f0)

        f0_s = prosody.get("f0_std_hz")
        if f0_s is not None:
            f0_stds.append(f0_s)

        rms = audio.get("rms_db", None)
        if rms is not None:
            rms_values.append(rms)

        cent = audio.get("spectral_centroid_hz", None)
        if cent is not None and cent > 0:
            centroids.append(cent)

        pb = prosody.get("pause_before_ms", 0)
        if pb > 0:
            pauses.append(pb)

    # Also extract from prosody_map directly for richer baseline
    for p in prosody_map:
        rate = p.get("speech_rate_wps", 0.0)
        if rate > 0:
            speech_rates.append(rate)
        f0 = p.get("f0_mean_hz")
        if f0 is not None and f0 > 0:
            f0_means.append(f0)
        f0_s = p.get("f0_std_hz")
        if f0_s is not None:
            f0_stds.append(f0_s)

    sample_count = len(issue_records)

    baseline = {
        "sample_count": sample_count,
        "is_stable": sample_count >= MIN_SEGMENTS_FOR_STABLE_BASELINE,
        "blend_ratio": 1.0 if sample_count >= MIN_SEGMENTS_FOR_STABLE_BASELINE else BLEND_RATIO_UNSTABLE,
        "mean_speech_rate": _safe_mean(speech_rates, 3.0),
        "std_speech_rate": _safe_std(speech_rates, 1.0),
        "mean_f0": _safe_mean(f0_means, 150.0),
        "std_f0": _safe_std(f0_means, 30.0),
        "mean_f0_std": _safe_mean(f0_stds, 20.0),
        "std_f0_std": _safe_std(f0_stds, 10.0),
        "mean_rms_db": _safe_mean(rms_values, -20.0),
        "std_rms_db": _safe_std(rms_values, 5.0),
        "mean_spectral_centroid": _safe_mean(centroids, 1500.0),
        "std_spectral_centroid": _safe_std(centroids, 500.0),
        "mean_pause": _safe_mean(pauses, 200.0),
        "std_pause": _safe_std(pauses, 150.0),
    }

    return baseline


def _safe_mean(values: list[float], default: float) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def _safe_std(values: list[float], default: float) -> float:
    if len(values) < 2:
        return default
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return variance ** 0.5
