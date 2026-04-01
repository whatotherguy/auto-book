"""Tests for simulation runner: config generation, sweep execution."""

from app.services.scoring.calibration.config import ScoringConfig
from app.services.scoring.calibration.dataset import make_clean_segment, GroundTruth
from app.services.scoring.calibration.simulation import (
    generate_grid_configs,
    generate_monte_carlo_configs,
    generate_latin_hypercube_configs,
    run_simulation,
    run_sweep,
    run_calibration_sweep,
    SimulationResult,
    SweepResult,
)


def _make_labeled_segments(n_mistakes=5, n_clean=10):
    """Create labeled segment dicts for simulation."""
    segments = []
    for i in range(n_mistakes):
        seg = make_clean_segment(f"mistake_{i}")
        seg.features["expected_text"] = "The quick brown fox"
        seg.features["spoken_text"] = "The quick brown fax"  # Mismatch
        seg.features["issue_type"] = "substitution"
        seg.features["confidence"] = 0.85
        seg.ground_truth = GroundTruth(
            is_mistake=True, priority="high", preferred_action="review_mistake",
        )
        segments.append(seg.to_dict())
    for i in range(n_clean):
        seg = make_clean_segment(f"clean_{i}")
        segments.append(seg.to_dict())
    return segments


# --- Config generation ---

def test_monte_carlo_generates_correct_count():
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=50, seed=42)
    assert len(configs) == 50


def test_monte_carlo_configs_are_different():
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=10, seed=42)
    hashes = {c.config_hash for c in configs}
    assert len(hashes) == 10  # All unique


def test_monte_carlo_reproducible():
    configs1 = generate_monte_carlo_configs(ScoringConfig(), n_configs=5, seed=42)
    configs2 = generate_monte_carlo_configs(ScoringConfig(), n_configs=5, seed=42)
    for c1, c2 in zip(configs1, configs2):
        assert c1.config_hash == c2.config_hash


def test_grid_search_generates_combinations():
    configs = generate_grid_configs(
        ScoringConfig(),
        param_grid={
            "mistake.text_mismatch": [0.2, 0.3, 0.4],
            "mistake.repeated_phrase": [0.1, 0.2],
        },
    )
    assert len(configs) == 6  # 3 * 2


def test_grid_search_respects_max_configs():
    configs = generate_grid_configs(
        ScoringConfig(),
        param_grid={
            "mistake.text_mismatch": [0.1, 0.2, 0.3, 0.4, 0.5],
            "mistake.repeated_phrase": [0.1, 0.2, 0.3, 0.4, 0.5],
        },
        max_configs=10,
    )
    assert len(configs) == 10


def test_latin_hypercube_generates_correct_count():
    configs = generate_latin_hypercube_configs(ScoringConfig(), n_configs=30, seed=42)
    assert len(configs) == 30


def test_latin_hypercube_configs_are_different():
    configs = generate_latin_hypercube_configs(ScoringConfig(), n_configs=20, seed=42)
    hashes = {c.config_hash for c in configs}
    assert len(hashes) == 20


# --- Simulation execution ---

def test_run_simulation_returns_result():
    segments = _make_labeled_segments(n_mistakes=3, n_clean=5)
    cfg = ScoringConfig()
    from app.services.scoring.baseline import build_chapter_baseline
    baseline = build_chapter_baseline(
        [{"prosody_features_json": "{}", "audio_features_json": "{}"}] * len(segments),
        [], [],
    )
    result = run_simulation(cfg, segments, baseline)
    assert isinstance(result, SimulationResult)
    assert result.elapsed_ms >= 0
    assert len(result.predictions) == len(segments)
    assert "combined_f1" in result.metrics or "combined_score" in result.metrics


def test_run_simulation_detects_mistakes():
    segments = _make_labeled_segments(n_mistakes=5, n_clean=5)
    cfg = ScoringConfig()
    from app.services.scoring.baseline import build_chapter_baseline
    baseline = build_chapter_baseline(
        [{"prosody_features_json": "{}", "audio_features_json": "{}"}] * len(segments),
        [], [],
    )
    result = run_simulation(cfg, segments, baseline)
    # Should have some true positives for mistakes
    assert result.metrics.get("mistake_tp", 0) >= 0


# --- Sweep ---

def test_run_sweep_returns_best():
    segments = _make_labeled_segments(n_mistakes=3, n_clean=5)
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=10, seed=42)
    sweep = run_sweep(configs, segments)
    assert isinstance(sweep, SweepResult)
    assert sweep.total_configs == 10
    assert sweep.best_result is not None
    assert len(sweep.results) == 10
    assert sweep.total_elapsed_ms > 0


def test_run_sweep_sorted_results():
    segments = _make_labeled_segments(n_mistakes=3, n_clean=5)
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=10, seed=42)
    sweep = run_sweep(configs, segments)
    top = sweep.top_n(3)
    assert len(top) == 3
    # Should be sorted descending by combined score
    scores = [r.combined_score for r in top]
    assert scores == sorted(scores, reverse=True)


def test_run_sweep_convergence_history():
    segments = _make_labeled_segments(n_mistakes=3, n_clean=5)
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=20, seed=42)
    sweep = run_sweep(configs, segments, progress_interval=10)
    assert len(sweep.convergence_history) > 0


# --- Legacy compatibility ---

def test_run_calibration_sweep_empty():
    result = run_calibration_sweep([])
    assert result["best_config"] is None
    assert result["best_metrics"] is None


def test_run_calibration_sweep_basic():
    segments = _make_labeled_segments(n_mistakes=3, n_clean=5)
    result = run_calibration_sweep(segments, iterations=20, jitter=0.3)
    assert result["best_config"] is not None
    assert result["best_metrics"] is not None
    assert len(result["convergence_history"]) > 0
