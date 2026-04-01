"""Tests for the BlitzHarness orchestrator — end-to-end calibration workflow."""

from pathlib import Path

from app.services.scoring.calibration.config import ScoringConfig
from app.services.scoring.calibration.dataset import (
    CalibrationDataset,
    GroundTruth,
    make_clean_segment,
)
from app.services.scoring.calibration.harness import BlitzHarness, BlitzResult
from app.services.scoring.calibration.optimizer import ObjectiveWeights


def _make_test_dataset():
    """Build a small mixed dataset for testing."""
    segments = []
    # Mistakes: text mismatch
    for i in range(8):
        seg = make_clean_segment(f"mistake_{i}", narrator_id="narrator_a")
        seg.features["expected_text"] = "The quick brown fox jumps over the lazy dog"
        seg.features["spoken_text"] = "The quick brown fax jumps over the lazy dog"
        seg.features["issue_type"] = "substitution"
        seg.features["confidence"] = 0.85
        seg.ground_truth = GroundTruth(
            is_mistake=True, priority="high", preferred_action="review_mistake",
            needs_review=True, mistake_type="text_mismatch",
        )
        segments.append(seg)

    # Pickups: restart pattern
    for i in range(5):
        seg = make_clean_segment(f"pickup_{i}", narrator_id="narrator_b")
        seg.features["issue_type"] = "pickup_restart"
        seg.features["confidence"] = 0.75
        seg.features["pause_before_ms"] = 800
        seg.features["has_silence_gap"] = True
        seg.features["silence_gap_ms"] = 800
        seg.features["restart_pattern_detected"] = True
        seg.features["has_click_marker"] = True
        seg.features["click_marker_confidence"] = 0.7
        seg.ground_truth = GroundTruth(
            is_mistake=False, is_pickup=True, priority="medium",
            preferred_action="likely_pickup", needs_review=True,
        )
        segments.append(seg)

    # Clean segments
    for i in range(15):
        seg = make_clean_segment(
            f"clean_{i}",
            narrator_id="narrator_a" if i % 2 == 0 else "narrator_b",
        )
        segments.append(seg)

    return CalibrationDataset(name="test_harness", segments=segments)


# --- Basic workflow ---

def test_harness_generate_synthetic():
    harness = BlitzHarness()
    ds = harness.generate_synthetic_dataset(n_per_type=5, n_clean=10)
    assert ds.segment_count > 0
    assert ds.name.startswith("synthetic_")


def test_harness_set_dataset():
    harness = BlitzHarness()
    ds = _make_test_dataset()
    harness.set_dataset(ds)
    assert harness.dataset is not None
    assert harness.baseline is not None


def test_harness_run_blitz_monte_carlo():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    result = harness.run_blitz(strategy="monte_carlo", n_configs=20, seed=42)

    assert isinstance(result, BlitzResult)
    assert result.sweep.total_configs == 20
    assert result.best_config is not None
    assert result.best_score > 0
    assert len(result.report) > 0
    assert result.elapsed_total_ms > 0


def test_harness_run_blitz_grid():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    result = harness.run_blitz(
        strategy="grid",
        param_grid={
            "mistake.text_mismatch": [0.25, 0.35, 0.45],
            "rec.mistake_trigger": [0.4, 0.5, 0.6],
        },
    )
    assert result.sweep.total_configs == 9  # 3 * 3


def test_harness_run_blitz_latin_hypercube():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    result = harness.run_blitz(strategy="latin_hypercube", n_configs=15)
    assert result.sweep.total_configs == 15


def test_harness_run_blitz_with_custom_objectives():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    result = harness.run_blitz(
        n_configs=10,
        objective_weights=ObjectiveWeights.high_recall(),
    )
    assert result.optimization.objective_weights.mistake_f1 == 0.35


# --- Ablation ---

def test_harness_run_ablation():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    result = harness.run_blitz(n_configs=10, run_ablation=True)
    assert len(result.ablation) > 0
    # Each entry should have detector name and delta
    for entry in result.ablation:
        assert "detector" in entry
        assert "delta" in entry
        assert "impact" in entry


def test_harness_standalone_ablation():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    ablation = harness.run_ablation_test()
    assert len(ablation) > 0


# --- Threshold sweep ---

def test_harness_threshold_sweep():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    curve = harness.run_threshold_sweep(
        score_field="mistake_score", truth_field="is_mistake",
    )
    assert len(curve) > 0
    assert all("threshold" in p for p in curve)
    assert all("f1" in p for p in curve)


# --- Noise robustness ---

def test_harness_noise_robustness():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    results = harness.run_noise_robustness_test(noise_levels=[0.0, 0.5, 1.0])
    assert len(results) == 3
    # Score at noise=0 should be >= score at noise=1 (usually)
    assert results[0]["noise_level"] == 0.0
    assert results[2]["noise_level"] == 1.0


# --- Drift test ---

def test_harness_drift_test():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    results = harness.run_drift_test(n_positions=5)
    assert len(results) == 5
    assert results[0]["session_position"] == 0.0
    assert results[-1]["session_position"] == 1.0


# --- Export ---

def test_harness_export(tmp_path):
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    harness.run_blitz(n_configs=10)
    paths = harness.export(tmp_path / "output")
    assert "best_config" in paths
    assert "report" in paths
    assert "production_config" in paths
    assert paths["best_config"].exists()
    assert paths["report"].exists()


def test_harness_export_with_ablation(tmp_path):
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    harness.run_blitz(n_configs=10, run_ablation=True)
    paths = harness.export(tmp_path / "output")
    assert "ablation" in paths
    assert paths["ablation"].exists()


# --- Config store ---

def test_harness_save_best_config(tmp_path):
    harness = BlitzHarness(config_store_dir=tmp_path / "configs")
    harness.set_dataset(_make_test_dataset())
    harness.run_blitz(n_configs=10)
    path = harness.save_best_config("best_v1")
    assert path is not None
    assert path.exists()


# --- Narrator calibration ---

def test_harness_narrator_calibration():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    results = harness.run_narrator_calibration(n_configs=10)
    # Should have results for narrators with enough segments
    assert isinstance(results, dict)


# --- Error handling ---

def test_harness_raises_without_dataset():
    harness = BlitzHarness()
    try:
        harness.run_blitz()
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "No dataset" in str(e)


def test_harness_grid_search_requires_param_grid():
    harness = BlitzHarness()
    harness.set_dataset(_make_test_dataset())
    try:
        harness.run_blitz(strategy="grid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "param_grid" in str(e)


# --- Reproducibility ---

def test_harness_blitz_reproducible():
    ds = _make_test_dataset()

    harness1 = BlitzHarness()
    harness1.set_dataset(ds)
    result1 = harness1.run_blitz(n_configs=20, seed=42)

    harness2 = BlitzHarness()
    harness2.set_dataset(ds)
    result2 = harness2.run_blitz(n_configs=20, seed=42)

    assert result1.best_config.config_hash == result2.best_config.config_hash
    assert result1.best_score == result2.best_score
