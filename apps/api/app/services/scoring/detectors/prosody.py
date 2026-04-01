"""Prosody-based detectors: FlatDelivery, WeakLanding, CadenceDrift."""

from __future__ import annotations

from ..detector_output import DetectorOutput


def detect_flat_delivery(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect flat/monotone delivery based on F0 variation."""
    f0_std = features.get("f0_std_hz")
    z_f0_std = derived.get("z_f0_std", 0.0)
    speech_rate = features.get("speech_rate_wps", 0.0)

    score = 0.0
    reasons = []

    if f0_std is not None and f0_std < 10.0:
        score = min(1.0, (15.0 - f0_std) / 15.0)
        reasons.append(f"f0_std={f0_std:.1f}Hz (low variation)")

    if z_f0_std < -1.5:
        score = max(score, min(1.0, abs(z_f0_std) / 3.0))
        reasons.append(f"z_f0_std={z_f0_std:.2f}")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="flat_delivery",
        score=min(1.0, score),
        confidence=0.6 if f0_std is not None else 0.3,
        reasons=reasons,
        features_used={"f0_std_hz": f0_std, "z_f0_std": z_f0_std},
        triggered=triggered,
    )


def detect_weak_landing(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect weak sentence landings (energy drop at end)."""
    energy_contour = features.get("energy_contour", [])
    is_last_in_sentence = features.get("is_last_sentence", False)

    score = 0.0
    reasons = []

    if len(energy_contour) >= 4:
        last_quarter = energy_contour[-(len(energy_contour) // 4):]
        first_quarter = energy_contour[:len(energy_contour) // 4]
        mean_last = sum(last_quarter) / len(last_quarter) if last_quarter else 0
        mean_first = sum(first_quarter) / len(first_quarter) if first_quarter else 0

        if mean_first > 0 and mean_last / mean_first < 0.3:
            score = min(1.0, 1.0 - (mean_last / mean_first))
            reasons.append(f"energy_drop_ratio={mean_last / mean_first:.2f}")

    if is_last_in_sentence:
        score *= 0.7  # Expected to trail off at sentence end
        reasons.append("sentence_end_expected")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="weak_landing",
        score=min(1.0, score),
        confidence=0.55,
        reasons=reasons,
        features_used={"energy_contour_len": len(energy_contour), "is_last_in_sentence": is_last_in_sentence},
        triggered=triggered,
    )


def detect_cadence_drift(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect cadence drift compared to neighbors."""
    z_rate = derived.get("z_speech_rate", 0.0)
    delta_rate_prev = derived.get("delta_speech_rate_prev", 0.0)
    delta_rate_next = derived.get("delta_speech_rate_next", 0.0)

    score = 0.0
    reasons = []

    if abs(z_rate) > 1.5:
        score = min(1.0, abs(z_rate) / 3.0)
        reasons.append(f"z_speech_rate={z_rate:.2f}")

    if abs(delta_rate_prev) > 1.5 and abs(delta_rate_next) > 1.5:
        # Both neighbors differ — this segment is an outlier
        score = max(score, min(1.0, (abs(delta_rate_prev) + abs(delta_rate_next)) / 6.0))
        reasons.append(f"delta_prev={delta_rate_prev:.2f}, delta_next={delta_rate_next:.2f}")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="cadence_drift",
        score=min(1.0, score),
        confidence=0.55,
        reasons=reasons,
        features_used={"z_speech_rate": z_rate, "delta_rate_prev": delta_rate_prev, "delta_rate_next": delta_rate_next},
        triggered=triggered,
    )
