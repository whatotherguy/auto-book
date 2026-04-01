"""Tests for perturbation engine: all 8 types, reproducibility, ground truth."""

import copy

from app.services.scoring.calibration.dataset import make_clean_segment
from app.services.scoring.calibration.perturbations import (
    PerturbationSpec,
    PERTURBATION_TYPES,
    apply_perturbation,
    ground_truth_for_perturbation,
    generate_synthetic_dataset,
    apply_session_drift,
    apply_noise_degradation,
)


def _clean_features():
    return make_clean_segment("test").features


# --- Individual perturbation types ---

def test_click_injection():
    feat = _clean_features()
    spec = PerturbationSpec(type="click_injection", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["has_click_marker"] is True
    assert result["click_marker_confidence"] > 0.5
    assert result["crest_factor"] >= 12.0


def test_silence_expansion():
    feat = _clean_features()
    spec = PerturbationSpec(type="silence_expansion", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["pause_before_ms"] >= 1500
    assert result["has_silence_gap"] is True
    assert result["silence_gap_ms"] > 0


def test_silence_compression():
    feat = _clean_features()
    feat["pause_before_ms"] = 500
    spec = PerturbationSpec(type="silence_compression", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["pause_before_ms"] < 200


def test_repeated_phrase():
    feat = _clean_features()
    spec = PerturbationSpec(type="repeated_phrase", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["issue_type"] == "repetition"
    assert result["confidence"] >= 0.80
    # Spoken text should be longer (has repeated words)
    assert len(result["spoken_text"].split()) > len(feat["spoken_text"].split())


def test_restart_simulation():
    feat = _clean_features()
    spec = PerturbationSpec(type="restart_simulation", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["issue_type"] == "pickup_restart"
    assert result["restart_pattern_detected"] is True
    assert result["has_silence_gap"] is True


def test_pacing_change():
    feat = _clean_features()
    spec = PerturbationSpec(type="pacing_change", seed=42)
    result = apply_perturbation(feat, spec)
    # Rate should be significantly different from base 3.0
    assert abs(result["speech_rate_wps"] - 3.0) > 0.5


def test_gain_shift():
    feat = _clean_features()
    spec = PerturbationSpec(type="gain_shift", seed=42)
    result = apply_perturbation(feat, spec)
    # RMS should differ from original -20 dB
    assert abs(result["rms_db"] - (-20.0)) > 3.0


def test_clipping_simulation():
    feat = _clean_features()
    spec = PerturbationSpec(type="clipping_simulation", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["rms_db"] > -5.0
    assert result["crest_factor"] < 6.0


def test_combined_perturbation():
    feat = _clean_features()
    spec = PerturbationSpec(type="combined", seed=42)
    result = apply_perturbation(feat, spec)
    # Should have mutations from at least 2 types
    assert result != feat


# --- Reproducibility ---

def test_perturbation_is_reproducible():
    feat = _clean_features()
    spec = PerturbationSpec(type="click_injection", seed=12345)
    result1 = apply_perturbation(feat, spec)
    result2 = apply_perturbation(feat, spec)
    assert result1 == result2


def test_different_seeds_produce_different_results():
    feat = _clean_features()
    result1 = apply_perturbation(feat, PerturbationSpec(type="click_injection", seed=1))
    result2 = apply_perturbation(feat, PerturbationSpec(type="click_injection", seed=2))
    # At least some fields should differ
    assert result1["click_marker_confidence"] != result2["click_marker_confidence"]


def test_perturbation_does_not_mutate_input():
    feat = _clean_features()
    original = copy.deepcopy(feat)
    apply_perturbation(feat, PerturbationSpec(type="click_injection", seed=42))
    assert feat == original


# --- Parameterization ---

def test_click_injection_custom_intensity():
    feat = _clean_features()
    spec = PerturbationSpec(type="click_injection", params={"intensity": 1.0}, seed=42)
    result = apply_perturbation(feat, spec)
    assert result["click_marker_confidence"] == 1.0


def test_silence_expansion_custom_factor():
    feat = _clean_features()
    feat["pause_before_ms"] = 200
    spec = PerturbationSpec(type="silence_expansion", params={"factor": 10.0}, seed=42)
    result = apply_perturbation(feat, spec)
    assert result["pause_before_ms"] >= 2000


# --- Ground truth labels ---

def test_ground_truth_for_all_types():
    for p_type in list(PERTURBATION_TYPES.keys()) + ["combined"]:
        gt = ground_truth_for_perturbation(p_type)
        assert gt.annotator == "synthetic"
        # Ensure action is valid
        assert gt.preferred_action in [
            "no_action", "review_mistake", "likely_pickup",
            "manual_review_required", "safe_auto_cut",
        ]


def test_mistake_perturbation_labeled_as_mistake():
    gt = ground_truth_for_perturbation("repeated_phrase")
    assert gt.is_mistake is True
    assert gt.preferred_action == "review_mistake"


def test_restart_perturbation_labeled_as_pickup():
    gt = ground_truth_for_perturbation("restart_simulation")
    assert gt.is_pickup is True
    assert gt.preferred_action == "likely_pickup"


# --- Synthetic dataset generation ---

def test_generate_synthetic_dataset():
    base = [_clean_features() for _ in range(5)]
    segments = generate_synthetic_dataset(base, n_per_type=3, seed=42)
    assert len(segments) > 0
    # Should have clean + perturbed
    types = {s.perturbation_type for s in segments}
    assert "clean" in types
    assert "click_injection" in types


def test_generate_synthetic_dataset_reproducible():
    base = [_clean_features() for _ in range(3)]
    seg1 = generate_synthetic_dataset(base, n_per_type=2, seed=99)
    seg2 = generate_synthetic_dataset(base, n_per_type=2, seed=99)
    ids1 = [s.segment_id for s in seg1]
    ids2 = [s.segment_id for s in seg2]
    assert ids1 == ids2


def test_generate_synthetic_dataset_subset_types():
    base = [_clean_features() for _ in range(3)]
    segments = generate_synthetic_dataset(
        base, n_per_type=2, seed=42,
        perturbation_types=["click_injection", "clipping_simulation"],
        include_clean=False,
    )
    types = {s.perturbation_type for s in segments}
    assert types == {"click_injection", "clipping_simulation"}


# --- Session drift ---

def test_session_drift_start_minimal():
    feat = _clean_features()
    drifted = apply_session_drift(feat, session_position=0.0)
    # At start, drift should be minimal
    assert abs(drifted["speech_rate_wps"] - feat["speech_rate_wps"]) < 0.2


def test_session_drift_end_significant():
    feat = _clean_features()
    drifted = apply_session_drift(feat, session_position=1.0, drift_intensity=1.0)
    # At end, expect measurable changes
    assert drifted["speech_rate_wps"] < feat["speech_rate_wps"]
    assert drifted["f0_std_hz"] < feat["f0_std_hz"]
    assert drifted["rms_db"] < feat["rms_db"]


def test_session_drift_progressive():
    feat = _clean_features()
    early = apply_session_drift(feat, session_position=0.2, seed=42)
    late = apply_session_drift(feat, session_position=0.8, seed=42)
    # Later in session: slower speech, less pitch variation
    assert late["speech_rate_wps"] <= early["speech_rate_wps"]
    assert late["f0_std_hz"] <= early["f0_std_hz"]


# --- Noise degradation ---

def test_noise_degradation_clean():
    feat = _clean_features()
    noisy = apply_noise_degradation(feat, noise_level=0.0)
    assert noisy["rms_db"] == feat["rms_db"]
    assert noisy["whisper_word_confidence"] == feat["whisper_word_confidence"]


def test_noise_degradation_severe():
    feat = _clean_features()
    noisy = apply_noise_degradation(feat, noise_level=1.0)
    assert noisy["rms_db"] > feat["rms_db"]
    assert noisy["whisper_word_confidence"] < feat["whisper_word_confidence"]
    assert noisy["zero_crossing_rate"] > feat["zero_crossing_rate"]
