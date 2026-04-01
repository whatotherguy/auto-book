"""5 composite scoring formulas."""

from __future__ import annotations

from typing import Any

from ...detection_config import (
    CONTINUITY_WEIGHTS,
    MISTAKE_WEIGHTS,
    PERFORMANCE_WEIGHTS,
    PICKUP_WEIGHTS,
)
from .detector_output import DetectorOutput


def _weighted_sum(detector_outputs: dict[str, DetectorOutput], weights: dict[str, float]) -> tuple[float, float, dict[str, float], list[str]]:
    """Compute weighted sum of detector scores, returning (score, confidence, components, reasons)."""
    total = 0.0
    weight_sum = 0.0
    confidence_sum = 0.0
    components: dict[str, float] = {}
    reasons: list[str] = []

    for detector_name, weight in weights.items():
        output = detector_outputs.get(detector_name)
        if output is None:
            continue
        abs_weight = abs(weight)
        if weight < 0:
            # Negative weights: higher detector score = lower composite score
            contribution = (1.0 - output.score) * abs_weight
        else:
            contribution = output.score * abs_weight
        total += contribution
        weight_sum += abs_weight
        confidence_sum += output.confidence * abs_weight
        components[detector_name] = round(output.score, 4)
        if output.triggered:
            reasons.extend(output.reasons[:2])

    if weight_sum > 0:
        score = total / weight_sum
        confidence = confidence_sum / weight_sum
    else:
        score = 0.0
        confidence = 0.0

    return min(1.0, score), min(1.0, confidence), components, reasons


def compute_mistake_candidate(detector_outputs: dict[str, DetectorOutput], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Compute mistake candidate composite score."""
    w = weights or MISTAKE_WEIGHTS
    score, confidence, components, reasons = _weighted_sum(detector_outputs, w)
    ambiguity = _check_ambiguity(detector_outputs, "mistake")
    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "components": components,
        "reasons": reasons,
        "ambiguity_flags": ambiguity,
    }


def compute_pickup_candidate(detector_outputs: dict[str, DetectorOutput], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Compute pickup candidate composite score."""
    w = weights or PICKUP_WEIGHTS
    score, confidence, components, reasons = _weighted_sum(detector_outputs, w)
    ambiguity = _check_ambiguity(detector_outputs, "pickup")
    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "components": components,
        "reasons": reasons,
        "ambiguity_flags": ambiguity,
    }


def compute_performance_quality(detector_outputs: dict[str, DetectorOutput], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Compute performance quality composite score (inverted — higher = better quality)."""
    w = weights or PERFORMANCE_WEIGHTS
    score, confidence, components, reasons = _weighted_sum(detector_outputs, w)
    ambiguity = _check_ambiguity(detector_outputs, "performance")
    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "components": components,
        "reasons": reasons,
        "ambiguity_flags": ambiguity,
    }


def compute_continuity_fit(detector_outputs: dict[str, DetectorOutput], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Compute continuity fit composite score (higher = better continuity)."""
    w = weights or CONTINUITY_WEIGHTS
    score, confidence, components, reasons = _weighted_sum(detector_outputs, w)
    ambiguity = _check_ambiguity(detector_outputs, "continuity")
    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "components": components,
        "reasons": reasons,
        "ambiguity_flags": ambiguity,
    }


def compute_splice_readiness(detector_outputs: dict[str, DetectorOutput]) -> dict[str, Any]:
    """Compute splice readiness — how safely this segment can be auto-cut."""
    click = detector_outputs.get("click_transient")
    punch = detector_outputs.get("punch_in_boundary")
    continuity = detector_outputs.get("continuity_mismatch")
    room_tone = detector_outputs.get("room_tone_shift")

    # Splice-ready if: clear boundaries, no continuity issues, clean audio
    score = 0.5  # Base
    components: dict[str, float] = {}
    reasons: list[str] = []

    if punch and punch.triggered:
        score += 0.2
        components["punch_in_boundary"] = punch.score
        reasons.append("clear_edit_boundary")

    if continuity and not continuity.triggered:
        score += 0.15
        components["continuity_ok"] = 1.0 - continuity.score

    if room_tone and not room_tone.triggered:
        score += 0.1
        components["room_tone_ok"] = 1.0 - room_tone.score

    if click and click.triggered:
        score -= 0.1
        components["click_present"] = click.score
        reasons.append("click_near_boundary")

    confidence = 0.7

    return {
        "score": round(min(1.0, max(0.0, score)), 4),
        "confidence": round(confidence, 4),
        "components": components,
        "reasons": reasons,
        "ambiguity_flags": [],
    }


def compute_all_composites(
    detector_outputs: dict[str, DetectorOutput],
    weights: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Compute all 5 composite scores."""
    w = weights or {}
    return {
        "mistake_candidate": compute_mistake_candidate(detector_outputs, w.get("mistake")),
        "pickup_candidate": compute_pickup_candidate(detector_outputs, w.get("pickup")),
        "performance_quality": compute_performance_quality(detector_outputs, w.get("performance")),
        "continuity_fit": compute_continuity_fit(detector_outputs, w.get("continuity")),
        "splice_readiness": compute_splice_readiness(detector_outputs),
    }


def _check_ambiguity(detector_outputs: dict[str, DetectorOutput], category: str) -> list[str]:
    """Check for ambiguity flags (conflicting detector signals)."""
    flags: list[str] = []
    triggered_count = sum(1 for d in detector_outputs.values() if d.triggered)
    low_confidence = [d.detector_name for d in detector_outputs.values() if d.triggered and d.confidence < 0.5]

    if triggered_count >= 4:
        flags.append("many_detectors_triggered")

    if low_confidence:
        flags.append(f"low_confidence_detectors: {', '.join(low_confidence[:3])}")

    return flags
