from app.services.scoring.detector_output import DetectorOutput
from app.services.scoring.composite import (
    compute_mistake_candidate,
    compute_pickup_candidate,
    compute_performance_quality,
    compute_continuity_fit,
    compute_splice_readiness,
    compute_all_composites,
    _weighted_sum,
)


def _make_output(name, score=0.0, confidence=0.8, triggered=False, reasons=None):
    return DetectorOutput(
        detector_name=name,
        score=score,
        confidence=confidence,
        triggered=triggered,
        reasons=reasons or [],
    )


def test_weighted_sum_basic():
    outputs = {
        "text_mismatch": _make_output("text_mismatch", score=0.9, triggered=True, reasons=["mismatch"]),
        "repeated_phrase": _make_output("repeated_phrase", score=0.0),
    }
    weights = {"text_mismatch": 0.6, "repeated_phrase": 0.4}
    score, confidence, components, reasons = _weighted_sum(outputs, weights)
    assert 0.5 < score < 0.6  # 0.9*0.6 / 1.0 = 0.54
    assert "text_mismatch" in components
    assert "mismatch" in reasons


def test_weighted_sum_negative_weight():
    """Negative weight means higher detector score reduces composite."""
    outputs = {
        "flat_delivery": _make_output("flat_delivery", score=0.9),
    }
    weights = {"flat_delivery": -0.5}
    score, _, _, _ = _weighted_sum(outputs, weights)
    assert score < 0.2  # (1.0 - 0.9) * 0.5 / 0.5 = 0.1


def test_weighted_sum_missing_detector():
    outputs = {"a": _make_output("a", score=0.5)}
    weights = {"a": 0.5, "missing": 0.5}
    score, _, _, _ = _weighted_sum(outputs, weights)
    # Only "a" contributes: 0.5 * 0.5 / 0.5 = 0.5
    assert score == 0.5


def test_weighted_sum_empty():
    score, confidence, components, reasons = _weighted_sum({}, {"a": 1.0})
    assert score == 0.0
    assert confidence == 0.0


def test_compute_mistake_candidate_high():
    outputs = {
        "text_mismatch": _make_output("text_mismatch", score=0.95, confidence=0.9, triggered=True),
        "repeated_phrase": _make_output("repeated_phrase", score=0.8, confidence=0.85, triggered=True),
    }
    result = compute_mistake_candidate(outputs)
    assert result["score"] > 0.5
    assert "components" in result
    assert "reasons" in result


def test_compute_mistake_candidate_custom_weights():
    outputs = {
        "text_mismatch": _make_output("text_mismatch", score=1.0, confidence=1.0),
    }
    result = compute_mistake_candidate(outputs, weights={"text_mismatch": 1.0})
    assert result["score"] == 1.0


def test_compute_pickup_candidate():
    outputs = {
        "pickup_pattern": _make_output("pickup_pattern", score=0.85, confidence=0.9, triggered=True),
        "restart_gap": _make_output("restart_gap", score=0.7, confidence=0.8, triggered=True),
    }
    result = compute_pickup_candidate(outputs)
    assert result["score"] > 0.5
    assert result["confidence"] > 0.5


def test_compute_performance_quality():
    outputs = {
        "flat_delivery": _make_output("flat_delivery", score=0.1),
        "weak_landing": _make_output("weak_landing", score=0.1),
    }
    result = compute_performance_quality(outputs)
    # Low scores with negative weights → high performance quality
    assert result["score"] > 0.7


def test_compute_splice_readiness_good():
    outputs = {
        "punch_in_boundary": _make_output("punch_in_boundary", score=0.9, triggered=True),
        "continuity_mismatch": _make_output("continuity_mismatch", score=0.1, triggered=False),
        "room_tone_shift": _make_output("room_tone_shift", score=0.1, triggered=False),
        "click_transient": _make_output("click_transient", score=0.1, triggered=False),
    }
    result = compute_splice_readiness(outputs)
    assert result["score"] >= 0.85
    assert "clear_edit_boundary" in result["reasons"]


def test_compute_splice_readiness_with_click():
    outputs = {
        "punch_in_boundary": _make_output("punch_in_boundary", score=0.9, triggered=True),
        "click_transient": _make_output("click_transient", score=0.8, triggered=True),
    }
    result = compute_splice_readiness(outputs)
    assert "click_near_boundary" in result["reasons"]
    # Score reduced by click
    assert result["score"] < 0.75


def test_compute_splice_readiness_empty():
    result = compute_splice_readiness({})
    assert result["score"] == 0.5  # Base score


def test_compute_all_composites():
    outputs = {
        "text_mismatch": _make_output("text_mismatch", score=0.5, confidence=0.7),
    }
    result = compute_all_composites(outputs)
    assert "mistake_candidate" in result
    assert "pickup_candidate" in result
    assert "performance_quality" in result
    assert "continuity_fit" in result
    assert "splice_readiness" in result


def test_ambiguity_many_triggered():
    outputs = {
        f"d{i}": _make_output(f"d{i}", score=0.8, triggered=True)
        for i in range(5)
    }
    result = compute_mistake_candidate(outputs, weights={f"d{i}": 0.2 for i in range(5)})
    assert "many_detectors_triggered" in result["ambiguity_flags"]


def test_ambiguity_low_confidence():
    outputs = {
        "text_mismatch": _make_output("text_mismatch", score=0.9, confidence=0.3, triggered=True),
    }
    result = compute_mistake_candidate(outputs, weights={"text_mismatch": 1.0})
    assert any("low_confidence" in f for f in result["ambiguity_flags"])
