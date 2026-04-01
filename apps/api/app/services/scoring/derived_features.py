"""Derived features: z-scores, deltas, ratios computed from baseline."""

from __future__ import annotations

from typing import Any


def compute_derived_features(
    features: dict[str, Any],
    baseline: dict[str, Any],
    prev_features: dict[str, Any] | None = None,
    next_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute z-scores, deltas, and ratios relative to chapter baseline."""
    derived: dict[str, Any] = {}

    # Z-scores
    derived["z_speech_rate"] = _z_score(
        features.get("speech_rate_wps", 0.0),
        baseline.get("mean_speech_rate", 3.0),
        baseline.get("std_speech_rate", 1.0),
    )

    derived["z_f0_mean"] = _z_score(
        features.get("f0_mean_hz") or 0.0,
        baseline.get("mean_f0", 150.0),
        baseline.get("std_f0", 30.0),
    ) if features.get("f0_mean_hz") is not None else 0.0

    derived["z_f0_std"] = _z_score(
        features.get("f0_std_hz") or 0.0,
        baseline.get("mean_f0_std", 20.0),
        baseline.get("std_f0_std", 10.0),
    ) if features.get("f0_std_hz") is not None else 0.0

    derived["z_rms_db"] = _z_score(
        features.get("rms_db", 0.0),
        baseline.get("mean_rms_db", -20.0),
        baseline.get("std_rms_db", 5.0),
    )

    derived["z_spectral_centroid"] = _z_score(
        features.get("spectral_centroid_hz", 0.0),
        baseline.get("mean_spectral_centroid", 1500.0),
        baseline.get("std_spectral_centroid", 500.0),
    )

    derived["z_pause_before"] = _z_score(
        features.get("pause_before_ms", 0.0),
        baseline.get("mean_pause", 200.0),
        baseline.get("std_pause", 150.0),
    )

    # Deltas from neighbors
    if prev_features:
        derived["delta_rms_db_prev"] = features.get("rms_db", 0.0) - prev_features.get("rms_db", 0.0)
        derived["delta_f0_prev"] = (features.get("f0_mean_hz") or 0.0) - (prev_features.get("f0_mean_hz") or 0.0)
        derived["delta_speech_rate_prev"] = features.get("speech_rate_wps", 0.0) - prev_features.get("speech_rate_wps", 0.0)
    else:
        # Use chapter means for edge segments
        derived["delta_rms_db_prev"] = features.get("rms_db", 0.0) - baseline.get("mean_rms_db", 0.0)
        derived["delta_f0_prev"] = (features.get("f0_mean_hz") or 0.0) - baseline.get("mean_f0", 0.0)
        derived["delta_speech_rate_prev"] = features.get("speech_rate_wps", 0.0) - baseline.get("mean_speech_rate", 0.0)

    if next_features:
        derived["delta_speech_rate_next"] = features.get("speech_rate_wps", 0.0) - next_features.get("speech_rate_wps", 0.0)
    else:
        derived["delta_speech_rate_next"] = features.get("speech_rate_wps", 0.0) - baseline.get("mean_speech_rate", 0.0)

    return derived


def _z_score(value: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.0
    return (value - mean) / std
