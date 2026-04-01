import json
from pathlib import Path
from app.services.scoring.calibration.labels import load_labeled_dataset, save_labeled_dataset, validate_label
from app.services.scoring.calibration.perturbations import inject_perturbation, generate_synthetic_dataset
from app.services.scoring.calibration.metrics import evaluate_predictions, _f1


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

def test_inject_text_mismatch():
    features = {"expected_text": "the quick brown fox", "confidence": 0.9}
    perturbed = inject_perturbation(features, "text_mismatch")
    assert perturbed["expected_text"] != features["expected_text"]
    assert perturbed["confidence"] < features["confidence"]


def test_inject_timing_anomaly():
    features = {"pause_before_ms": 100}
    perturbed = inject_perturbation(features, "timing_anomaly")
    assert perturbed["pause_before_ms"] >= 1500
    assert perturbed["has_silence_gap"] is True


def test_inject_audio_artifact():
    features = {}
    perturbed = inject_perturbation(features, "audio_artifact")
    assert perturbed["has_click_marker"] is True
    assert perturbed["rms_db"] > -5.0


def test_inject_prosody_shift():
    features = {"speech_rate_wps": 3.0, "f0_mean_hz": 150.0}
    perturbed = inject_perturbation(features, "prosody_shift")
    assert perturbed["speech_rate_wps"] > features["speech_rate_wps"]


def test_generate_synthetic_dataset():
    base = [{"speech_rate_wps": 3.0, "expected_text": "hello world", "f0_mean_hz": 150.0}]
    synthetic = generate_synthetic_dataset(base, n_perturbations_per_type=2)
    assert len(synthetic) == 10  # 5 types * 2
    for item in synthetic:
        assert "segment_id" in item
        assert "features" in item
        assert "ground_truth" in item


# --- Metrics ---

def test_f1_perfect():
    assert _f1(10, 0, 0) == 1.0


def test_f1_zero():
    assert _f1(0, 5, 5) == 0.0


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
    assert metrics["combined_f1"] > 0.9


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
