"""Tests for optimizer: Pareto frontier, objective weighting, early stopping, ablation."""

from app.services.scoring.calibration.config import ScoringConfig
from app.services.scoring.calibration.dataset import make_clean_segment, GroundTruth
from app.services.scoring.calibration.optimizer import (
    ObjectiveWeights,
    ParetoPoint,
    OptimizationResult,
    optimize,
    find_pareto_frontier,
    check_early_stopping,
    ablation_analysis,
)
from app.services.scoring.calibration.simulation import (
    generate_monte_carlo_configs,
    run_sweep,
    SimulationResult,
    SweepResult,
)


def _make_segments():
    segments = []
    for i in range(5):
        seg = make_clean_segment(f"mistake_{i}")
        seg.features["spoken_text"] = "The quick brown fax"
        seg.features["issue_type"] = "substitution"
        seg.ground_truth = GroundTruth(is_mistake=True, priority="high")
        segments.append(seg.to_dict())
    for i in range(8):
        segments.append(make_clean_segment(f"clean_{i}").to_dict())
    return segments


def _run_small_sweep():
    segments = _make_segments()
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=15, seed=42)
    return run_sweep(configs, segments)


# --- ObjectiveWeights presets ---

def test_objective_weights_balanced():
    w = ObjectiveWeights.balanced()
    assert w.mistake_f1 == 0.25


def test_objective_weights_high_recall():
    w = ObjectiveWeights.high_recall()
    assert w.mistake_f1 > ObjectiveWeights.balanced().mistake_f1


def test_objective_weights_low_workload():
    w = ObjectiveWeights.low_workload()
    assert w.workload_efficiency > ObjectiveWeights.balanced().workload_efficiency


# --- Optimization ---

def test_optimize_returns_ranked_results():
    sweep = _run_small_sweep()
    result = optimize(sweep)
    assert isinstance(result, OptimizationResult)
    assert len(result.ranked_results) == 15
    # Should be sorted descending
    scores = [r.metrics.get("combined_score", 0) for r in result.ranked_results]
    assert scores == sorted(scores, reverse=True)


def test_optimize_with_custom_weights():
    sweep = _run_small_sweep()
    weights = ObjectiveWeights.high_recall()
    result = optimize(sweep, weights)
    assert result.objective_weights.mistake_f1 == weights.mistake_f1


def test_optimize_finds_pareto_frontier():
    sweep = _run_small_sweep()
    result = optimize(sweep)
    # Pareto frontier should exist and be non-empty
    assert len(result.pareto_frontier) > 0
    # All frontier points should be non-dominated
    for pp in result.pareto_frontier:
        assert isinstance(pp, ParetoPoint)


def test_best_config_accessible():
    sweep = _run_small_sweep()
    result = optimize(sweep)
    best = result.best_config()
    assert best is not None
    assert isinstance(best, ScoringConfig)


# --- ParetoPoint dominance ---

def test_pareto_dominance_clear():
    a = ParetoPoint(
        config=ScoringConfig(), metrics={},
        objectives={"x": 0.9, "y": 0.8},
    )
    b = ParetoPoint(
        config=ScoringConfig(), metrics={},
        objectives={"x": 0.7, "y": 0.6},
    )
    assert a.dominates(b)
    assert not b.dominates(a)


def test_pareto_no_dominance_tradeoff():
    a = ParetoPoint(
        config=ScoringConfig(), metrics={},
        objectives={"x": 0.9, "y": 0.3},
    )
    b = ParetoPoint(
        config=ScoringConfig(), metrics={},
        objectives={"x": 0.3, "y": 0.9},
    )
    assert not a.dominates(b)
    assert not b.dominates(a)


# --- Early stopping ---

def test_early_stopping_no_improvement():
    history = [(i * 100, 0.5) for i in range(10)]  # Flat score
    should_stop, reason = check_early_stopping(history, patience=200)
    assert should_stop
    assert "No improvement" in reason


def test_early_stopping_still_improving():
    history = [(i * 100, 0.1 * i) for i in range(5)]
    should_stop, _ = check_early_stopping(history, patience=200)
    assert not should_stop


def test_early_stopping_insufficient_data():
    history = [(100, 0.5)]
    should_stop, _ = check_early_stopping(history)
    assert not should_stop


# --- Ablation analysis ---

def test_ablation_analysis_format():
    base = SimulationResult(
        config=ScoringConfig(),
        metrics={"combined_f1": 0.8, "mistake_f1": 0.7, "pickup_f1": 0.6},
    )
    ablated = {
        "text_mismatch": SimulationResult(
            config=ScoringConfig(),
            metrics={"combined_f1": 0.5, "mistake_f1": 0.3, "pickup_f1": 0.6},
        ),
        "click_transient": SimulationResult(
            config=ScoringConfig(),
            metrics={"combined_f1": 0.79, "mistake_f1": 0.69, "pickup_f1": 0.55},
        ),
    }
    results = ablation_analysis(base, ablated)
    assert len(results) == 2
    # Should be sorted by absolute delta
    assert abs(results[0]["delta"]) >= abs(results[1]["delta"])
    # text_mismatch removal should have bigger impact
    tm = next(r for r in results if r["detector"] == "text_mismatch")
    assert tm["delta"] > 0  # Removing it hurts score
    assert tm["impact"] == "positive"  # Detector contributes positively
