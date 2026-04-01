import json
from pathlib import Path
from app.services.scoring.calibration.labels import load_labeled_dataset, save_labeled_dataset, validate_label
from app.services.scoring.calibration.perturbations import (
    apply_perturbation, generate_synthetic_dataset, PerturbationSpec,
    ground_truth_for_perturbation, apply_session_drift, apply_noise_degradation,
)
from app.services.scoring.calibration.metrics import (
    evaluate_predictions, ClassificationMetrics, evaluate_full, compute_combined_score,
    confusion_matrix, score_distribution, threshold_sweep,
)


# --- Labels ---

def test_load_labeled_dataset_missing(tmp_path):
    result = load_labeled_dataset(tmp_path / "nonexistent")
    assert result == []


def test_save_and_load_dataset(tmp_path):
    dataset_path = tmp_path / "test_dataset"
    segments = [
        {"segment_id": "seg1", "features": {"speech_rate_wps": 3.0}, "ground_truth": {"is_mistake": True, "is_pickup": False}},
        {"segment_id": "seg2", "features": {"speech_rate_wps": 4.0}, "ground_truth": {"is_mistake": False, "is_pickup": True}},
    ]
    save_labeled_dataset(dataset_path, segments)
    loaded = load_labeled_dataset(dataset_path)
    assert len(loaded) == 2
    assert loaded[0]["segment_id"] == "seg1"


def test_validate_label_valid():
    label = {"segment_id": "s1", "features": {}, "ground_truth": {"is_mistake": True, "is_pickup": False}}
    errors = validate_label(label)
    assert errors == []


def test_validate_label_missing_fields():
    label = {"features": {}}
    errors = validate_label(label)
    assert "missing segment_id" in errors
    assert any("ground_truth" in e for e in errors)


# --- Perturbations ---

def test_apply_silence_expansion():
    features = {"pause_before_ms": 100}
    spec = PerturbationSpec(type="silence_expansion", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert perturbed["pause_before_ms"] >= 1500
    assert perturbed["has_silence_gap"] is True


def test_apply_click_injection():
    features = {}
    spec = PerturbationSpec(type="click_injection", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert perturbed["has_click_marker"] is True
    assert perturbed["crest_factor"] > 12.0


def test_apply_pacing_change():
    features = {"speech_rate_wps": 3.0, "duration_ms": 3000}
    spec = PerturbationSpec(type="pacing_change", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert perturbed["speech_rate_wps"] != features["speech_rate_wps"]


def test_apply_repeated_phrase():
    features = {"spoken_text": "the quick brown fox", "confidence": 0.9}
    spec = PerturbationSpec(type="repeated_phrase", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert len(perturbed["spoken_text"].split()) > len(features["spoken_text"].split())
    assert perturbed["issue_type"] == "repetition"


def test_apply_restart_simulation():
    features = {}
    spec = PerturbationSpec(type="restart_simulation", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert perturbed["issue_type"] == "pickup_restart"
    assert perturbed["restart_pattern_detected"] is True
    assert perturbed["has_silence_gap"] is True


def test_apply_gain_shift():
    features = {"rms_db": -20.0}
    spec = PerturbationSpec(type="gain_shift", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert perturbed["rms_db"] != features["rms_db"]


def test_apply_clipping():
    features = {}
    spec = PerturbationSpec(type="clipping_simulation", seed=42)
    perturbed = apply_perturbation(features, spec)
    assert perturbed["rms_db"] > -5.0
    assert perturbed["crest_factor"] < 6.0


def test_apply_combined_perturbation():
    features = {"speech_rate_wps": 3.0, "rms_db": -20.0, "pause_before_ms": 200}
    spec = PerturbationSpec(type="combined", seed=42)
    perturbed = apply_perturbation(features, spec)
    # Combined applies 2-3 types, so something should differ
    assert perturbed != features


def test_unknown_perturbation_type():
    import pytest
    features = {}
    spec = PerturbationSpec(type="nonexistent_type", seed=42)
    with pytest.raises(ValueError, match="Unknown perturbation type"):
        apply_perturbation(features, spec)


def test_ground_truth_for_perturbation():
    gt = ground_truth_for_perturbation("repeated_phrase")
    assert gt.is_mistake is True
    assert gt.priority == "high"

    gt2 = ground_truth_for_perturbation("restart_simulation")
    assert gt2.is_pickup is True

    gt3 = ground_truth_for_perturbation("silence_compression")
    assert gt3.needs_review is False


def test_generate_synthetic_dataset():
    base = [{"speech_rate_wps": 3.0, "spoken_text": "hello world", "rms_db": -20.0}]
    synthetic = generate_synthetic_dataset(base, n_per_type=2, seed=42)
    # 9 types * 2 + 1 clean = 19
    assert len(synthetic) == 19
    for item in synthetic:
        assert hasattr(item, "segment_id")
        assert hasattr(item, "features")
        assert hasattr(item, "ground_truth")


def test_generate_synthetic_dataset_no_clean():
    base = [{"speech_rate_wps": 3.0}]
    synthetic = generate_synthetic_dataset(base, n_per_type=1, seed=42, include_clean=False)
    assert all(s.perturbation_type != "clean" for s in synthetic)


def test_generate_synthetic_dataset_subset_types():
    base = [{"speech_rate_wps": 3.0}]
    synthetic = generate_synthetic_dataset(
        base, n_per_type=3, seed=42, include_clean=False,
        perturbation_types=["click_injection", "gain_shift"],
    )
    assert len(synthetic) == 6
    types = {s.perturbation_type for s in synthetic}
    assert types == {"click_injection", "gain_shift"}


def test_session_drift():
    features = {"speech_rate_wps": 3.0, "f0_std_hz": 25.0, "rms_db": -20.0, "pause_before_ms": 200}
    start = apply_session_drift(features, session_position=0.0, seed=42)
    end = apply_session_drift(features, session_position=1.0, seed=42)
    # End of session: slower speech, less f0 variation, lower energy, longer pauses
    assert end["speech_rate_wps"] < start["speech_rate_wps"]
    assert end["rms_db"] < start["rms_db"]


def test_noise_degradation():
    features = {"rms_db": -20.0, "spectral_centroid_hz": 1500, "whisper_word_confidence": 0.95}
    noisy = apply_noise_degradation(features, noise_level=0.8, seed=42)
    assert noisy["rms_db"] > features["rms_db"]
    assert noisy["spectral_centroid_hz"] > features["spectral_centroid_hz"]
    assert noisy["whisper_word_confidence"] < features["whisper_word_confidence"]


# --- Metrics ---

def test_classification_metrics_perfect():
    cm = ClassificationMetrics(tp=10, fp=0, fn=0, tn=5)
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.f1 == 1.0


def test_classification_metrics_zero():
    cm = ClassificationMetrics(tp=0, fp=5, fn=5, tn=0)
    assert cm.precision == 0.0
    assert cm.recall == 0.0
    assert cm.f1 == 0.0


def test_classification_metrics_empty():
    cm = ClassificationMetrics()
    assert cm.f1 == 0.0
    assert cm.accuracy == 0.0


def test_evaluate_predictions_perfect():
    predictions = [
        {"is_mistake": True, "is_pickup": False, "priority": "high"},
        {"is_mistake": False, "is_pickup": True, "priority": "medium"},
    ]
    ground_truths = [
        {"is_mistake": True, "is_pickup": False, "priority": "high"},
        {"is_mistake": False, "is_pickup": True, "priority": "medium"},
    ]
    metrics = evaluate_predictions(predictions, ground_truths)
    assert metrics["mistake_f1"] == 1.0
    assert metrics["pickup_f1"] == 1.0
    assert metrics["priority_accuracy"] == 1.0


def test_evaluate_predictions_empty():
    metrics = evaluate_predictions([], [])
    assert metrics["combined_f1"] == 0.0


def test_evaluate_predictions_all_wrong():
    predictions = [
        {"is_mistake": True, "is_pickup": True, "priority": "info"},
    ]
    ground_truths = [
        {"is_mistake": False, "is_pickup": False, "priority": "critical"},
    ]
    metrics = evaluate_predictions(predictions, ground_truths)
    assert metrics["mistake_f1"] == 0.0
    assert metrics["pickup_f1"] == 0.0
    assert metrics["priority_accuracy"] == 0.0


def test_confusion_matrix():
    preds = [{"is_mistake": True}, {"is_mistake": False}, {"is_mistake": True}]
    truths = [{"is_mistake": True}, {"is_mistake": True}, {"is_mistake": False}]
    cm = confusion_matrix(preds, truths, "is_mistake")
    assert cm["tp"] == 1
    assert cm["fn"] == 1
    assert cm["fp"] == 1
    assert cm["tn"] == 0


def test_score_distribution():
    results = [{"score": 0.1}, {"score": 0.5}, {"score": 0.9}]
    dist = score_distribution(results, "score", n_bins=2)
    assert dist["n"] == 3
    assert dist["min"] <= 0.1
    assert dist["max"] >= 0.9
    assert len(dist["bins"]) == 3  # n_bins + 1 edges


def test_score_distribution_empty():
    dist = score_distribution([], "score")
    assert dist["mean"] == 0.0
    assert dist["n"] == 0


def test_threshold_sweep():
    preds = [{"score": 0.3}, {"score": 0.7}, {"score": 0.9}]
    truths = [{"is_mistake": False}, {"is_mistake": True}, {"is_mistake": True}]
    curve = threshold_sweep(preds, truths, "score", "is_mistake", thresholds=[0.2, 0.5, 0.8])
    assert len(curve) == 3
    # At threshold 0.2, all 3 are positive → recall=1.0
    assert curve[0]["recall"] == 1.0
    # At threshold 0.8, only score=0.9 is positive → 1 TP, 1 FN
    assert curve[2]["recall"] == 0.5


def test_compute_combined_score_zeroed():
    metrics = {"workload": {"total_segments": 0}}
    assert compute_combined_score(metrics) == 0.0
