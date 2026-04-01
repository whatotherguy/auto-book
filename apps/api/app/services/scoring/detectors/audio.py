"""Audio-based detectors: ClickTransient, Clipping, RoomToneShift, PunchInBoundary."""

from __future__ import annotations

from ..detector_output import DetectorOutput


def detect_click_transient(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect click transients in the audio."""
    has_click = features.get("has_click_marker", False)
    click_confidence = features.get("click_marker_confidence", 0.0)

    score = 0.0
    reasons = []

    if has_click:
        score = click_confidence
        reasons.append(f"click_confidence={click_confidence:.2f}")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="click_transient",
        score=min(1.0, score),
        confidence=click_confidence if has_click else 0.0,
        reasons=reasons,
        features_used={"has_click_marker": has_click, "click_marker_confidence": click_confidence},
        triggered=triggered,
    )


def detect_clipping(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect audio clipping (signal saturation)."""
    rms_db = features.get("rms_db", -30.0)
    crest_factor = features.get("crest_factor", 0.0)

    score = 0.0
    reasons = []

    # High RMS close to 0 dBFS suggests clipping
    if rms_db > -3.0:
        score = min(1.0, (rms_db + 6.0) / 6.0)
        reasons.append(f"rms_db={rms_db:.1f} (near 0dBFS)")

    # Very low crest factor suggests sustained clipping
    if crest_factor < 3.0 and rms_db > -10.0:
        score = max(score, 0.6)
        reasons.append(f"low_crest_factor={crest_factor:.1f}")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="clipping",
        score=min(1.0, score),
        confidence=0.8 if score > 0.5 else 0.4,
        reasons=reasons,
        features_used={"rms_db": rms_db, "crest_factor": crest_factor},
        triggered=triggered,
    )


def detect_room_tone_shift(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect room tone shifts between segments."""
    z_rms = derived.get("z_rms_db", 0.0)
    z_centroid = derived.get("z_spectral_centroid", 0.0)
    delta_rms = derived.get("delta_rms_db_prev", 0.0)

    score = 0.0
    reasons = []

    if abs(z_rms) > 2.0:
        score = min(1.0, abs(z_rms) / 4.0)
        reasons.append(f"z_rms={z_rms:.2f}")

    if abs(delta_rms) > 6.0:
        score = max(score, min(1.0, abs(delta_rms) / 12.0))
        reasons.append(f"delta_rms={delta_rms:.1f}dB")

    if abs(z_centroid) > 2.5:
        score = max(score, 0.4)
        reasons.append(f"z_centroid={z_centroid:.2f}")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="room_tone_shift",
        score=min(1.0, score),
        confidence=0.6,
        reasons=reasons,
        features_used={"z_rms": z_rms, "delta_rms": delta_rms, "z_centroid": z_centroid},
        triggered=triggered,
    )


def detect_punch_in_boundary(features: dict, derived: dict, config: dict | None = None) -> DetectorOutput:
    """Detect punch-in edit boundaries."""
    has_cutoff = features.get("has_abrupt_cutoff", False)
    has_onset = features.get("has_onset_burst", False)
    has_click = features.get("has_click_marker", False)
    restart_pattern = features.get("restart_pattern_detected", False)

    score = 0.0
    reasons = []

    if has_cutoff and has_onset:
        score = 0.7
        reasons.append("cutoff+onset_burst")
    elif has_cutoff:
        score = 0.4
        reasons.append("abrupt_cutoff")

    if restart_pattern:
        score = max(score, 0.6)
        reasons.append("restart_pattern")

    if has_click and has_cutoff:
        score = max(score, 0.65)
        reasons.append("click+cutoff")

    triggered = score >= (config or {}).get("threshold", 0.3)

    return DetectorOutput(
        detector_name="punch_in_boundary",
        score=min(1.0, score),
        confidence=0.65,
        reasons=reasons,
        features_used={"has_cutoff": has_cutoff, "has_onset": has_onset, "restart_pattern": restart_pattern},
        triggered=triggered,
    )
