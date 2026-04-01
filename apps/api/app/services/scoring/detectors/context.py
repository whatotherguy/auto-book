"""Context-based detectors: PickupPattern, ContinuityMismatch."""

from __future__ import annotations

from ..detector_output import DetectorOutput


def detect_pickup_pattern(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect pickup/restart patterns from signal + text features."""
    issue_type = features.get("issue_type", "")
    restart_pattern = features.get("restart_pattern_detected", False)
    has_click = features.get("has_click_marker", False)
    has_silence = features.get("has_silence_gap", False)
    pause_before = features.get("pause_before_ms", 0)

    score = 0.0
    reasons = []

    if issue_type in ("pickup_restart", "pickup_candidate"):
        score = 0.7
        reasons.append(f"issue_type={issue_type}")

    if restart_pattern:
        score = max(score, 0.6)
        reasons.append("restart_pattern_detected")

    if has_click and has_silence and pause_before > 300:
        score = max(score, 0.5)
        reasons.append(f"click+silence+pause({pause_before}ms)")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="pickup_pattern",
        score=min(1.0, score),
        confidence=0.75 if issue_type in ("pickup_restart", "pickup_candidate") else 0.6,
        reasons=reasons,
        features_used={
            "issue_type": issue_type,
            "restart_pattern": restart_pattern,
            "has_click": has_click,
            "pause_before_ms": pause_before,
        },
        triggered=triggered,
    )


def detect_continuity_mismatch(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect continuity mismatches between adjacent segments."""
    delta_rms = derived.get("delta_rms_db_prev", 0.0)
    delta_f0 = derived.get("delta_f0_prev", 0.0)
    delta_rate = derived.get("delta_speech_rate_prev", 0.0)
    is_first = features.get("is_first_sentence", False)
    is_last = features.get("is_last_sentence", False)

    score = 0.0
    reasons = []

    # Reduce weight for edge segments
    edge_factor = 0.5 if (is_first or is_last) else 1.0

    if abs(delta_rms) > 4.0:
        score += min(0.4, abs(delta_rms) / 10.0)
        reasons.append(f"delta_rms={delta_rms:.1f}dB")

    if abs(delta_f0) > 30.0:
        score += min(0.3, abs(delta_f0) / 100.0)
        reasons.append(f"delta_f0={delta_f0:.1f}Hz")

    if abs(delta_rate) > 2.0:
        score += min(0.3, abs(delta_rate) / 6.0)
        reasons.append(f"delta_rate={delta_rate:.2f}wps")

    score = min(1.0, score * edge_factor)
    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="continuity_mismatch",
        score=score,
        confidence=0.5 * edge_factor + 0.2,
        reasons=reasons,
        features_used={
            "delta_rms": delta_rms,
            "delta_f0": delta_f0,
            "delta_rate": delta_rate,
            "is_edge": is_first or is_last,
        },
        triggered=triggered,
    )
