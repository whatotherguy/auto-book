"""Timing-based detectors: AbnormalPause, RestartGap, RushedDelivery."""

from __future__ import annotations

from ..detector_output import DetectorOutput


def detect_abnormal_pause(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect abnormally long pauses."""
    issue_type = features.get("issue_type", "")
    pause_before = features.get("pause_before_ms", 0)
    pause_after = features.get("pause_after_ms", 0)
    z_pause = derived.get("z_pause_before", 0.0)

    score = 0.0
    reasons = []

    if issue_type == "long_pause":
        duration_ms = features.get("end_ms", 0) - features.get("start_ms", 0)
        score = min(1.0, duration_ms / 5000)
        reasons.append(f"pause_duration={duration_ms}ms")

    if z_pause > 2.0:
        score = max(score, min(1.0, z_pause / 4.0))
        reasons.append(f"z_pause_before={z_pause:.2f}")

    if pause_before > 1500:
        score = max(score, 0.5)
        reasons.append(f"pause_before={pause_before}ms")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="abnormal_pause",
        score=min(1.0, score),
        confidence=0.85 if issue_type == "long_pause" else 0.7,
        reasons=reasons,
        features_used={"pause_before_ms": pause_before, "z_pause": z_pause},
        triggered=triggered,
    )


def detect_restart_gap(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect restart gaps (silence before re-reading)."""
    issue_type = features.get("issue_type", "")
    pause_before = features.get("pause_before_ms", 0)
    has_silence = features.get("has_silence_gap", False)
    silence_ms = features.get("silence_gap_ms", 0)

    score = 0.0
    reasons = []

    if issue_type in ("pickup_restart", "pickup_candidate"):
        score = 0.6
        reasons.append(f"detected_as={issue_type}")

    if has_silence and silence_ms > 300:
        score = max(score, min(1.0, silence_ms / 2000))
        reasons.append(f"silence_gap={silence_ms}ms")

    if pause_before > 500 and has_silence:
        score = max(score, 0.5)
        reasons.append(f"gap_with_silence={pause_before}ms")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="restart_gap",
        score=min(1.0, score),
        confidence=0.75,
        reasons=reasons,
        features_used={"pause_before_ms": pause_before, "silence_ms": silence_ms, "has_silence": has_silence},
        triggered=triggered,
    )


def detect_rushed_delivery(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect rushed delivery based on speech rate."""
    speech_rate = features.get("speech_rate_wps", 0.0)
    z_rate = derived.get("z_speech_rate", 0.0)

    score = 0.0
    reasons = []

    if z_rate > 2.0:
        score = min(1.0, (z_rate - 1.0) / 3.0)
        reasons.append(f"z_speech_rate={z_rate:.2f}")

    if speech_rate > 5.0:
        score = max(score, min(1.0, (speech_rate - 4.0) / 4.0))
        reasons.append(f"speech_rate={speech_rate:.1f}wps")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="rushed_delivery",
        score=min(1.0, score),
        confidence=0.7 if z_rate > 1.5 else 0.5,
        reasons=reasons,
        features_used={"speech_rate_wps": speech_rate, "z_speech_rate": z_rate},
        triggered=triggered,
    )
