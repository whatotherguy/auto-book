"""Multi-objective optimizer: Pareto frontier, early stopping, objective weighting."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import ScoringConfig
from .simulation import SimulationResult, SweepResult

logger = logging.getLogger(__name__)


@dataclass
class ObjectiveWeights:
    """Configurable weights for the combined objective function."""
    mistake_f1: float = 0.25
    pickup_f1: float = 0.20
    ranking_top1: float = 0.10
    splice_accuracy: float = 0.10
    workload_efficiency: float = 0.15
    priority_accuracy: float = 0.10
    action_accuracy: float = 0.10

    def to_dict(self) -> dict[str, float]:
        return {
            "mistake_f1": self.mistake_f1,
            "pickup_f1": self.pickup_f1,
            "ranking_top1": self.ranking_top1,
            "splice_accuracy": self.splice_accuracy,
            "workload_efficiency": self.workload_efficiency,
            "priority_accuracy": self.priority_accuracy,
            "action_accuracy": self.action_accuracy,
        }

    @classmethod
    def high_recall(cls) -> ObjectiveWeights:
        """Preset: maximize recall, tolerate more false positives."""
        return cls(mistake_f1=0.35, pickup_f1=0.25, workload_efficiency=0.05)

    @classmethod
    def low_workload(cls) -> ObjectiveWeights:
        """Preset: minimize editorial workload, accept missing some issues."""
        return cls(mistake_f1=0.15, pickup_f1=0.15, workload_efficiency=0.35)

    @classmethod
    def balanced(cls) -> ObjectiveWeights:
        """Preset: default balanced weighting."""
        return cls()


@dataclass
class ParetoPoint:
    """A single point on the Pareto frontier."""
    config: ScoringConfig
    metrics: dict[str, Any]
    objectives: dict[str, float]
    combined_score: float = 0.0

    def dominates(self, other: ParetoPoint) -> bool:
        """True if self is at least as good in all objectives and strictly better in one."""
        at_least_as_good = all(
            self.objectives.get(k, 0) >= other.objectives.get(k, 0)
            for k in self.objectives
        )
        strictly_better = any(
            self.objectives.get(k, 0) > other.objectives.get(k, 0)
            for k in self.objectives
        )
        return at_least_as_good and strictly_better


@dataclass
class OptimizationResult:
    """Result of optimization including ranked configs and Pareto frontier."""
    ranked_results: list[SimulationResult] = field(default_factory=list)
    pareto_frontier: list[ParetoPoint] = field(default_factory=list)
    objective_weights: ObjectiveWeights = field(default_factory=ObjectiveWeights)
    early_stopped: bool = False
    stop_reason: str = ""

    def best_config(self) -> ScoringConfig | None:
        return self.ranked_results[0].config if self.ranked_results else None

    def best_metrics(self) -> dict[str, Any]:
        return self.ranked_results[0].metrics if self.ranked_results else {}

    def pareto_configs(self) -> list[ScoringConfig]:
        return [p.config for p in self.pareto_frontier]


def optimize(
    sweep: SweepResult,
    objective_weights: ObjectiveWeights | None = None,
) -> OptimizationResult:
    """Rank sweep results and find Pareto frontier."""
    weights = objective_weights or ObjectiveWeights()

    result = OptimizationResult(objective_weights=weights)

    # Compute combined score for each result using custom weights
    for sim_result in sweep.results:
        sim_result.metrics["combined_score"] = _weighted_objective(sim_result.metrics, weights)

    # Rank by combined score
    result.ranked_results = sorted(
        sweep.results,
        key=lambda r: r.metrics.get("combined_score", 0.0),
        reverse=True,
    )

    # Find Pareto frontier
    result.pareto_frontier = _find_pareto_frontier(sweep.results, weights)

    return result


def find_pareto_frontier(
    sweep: SweepResult,
    objective_axes: list[str] | None = None,
) -> list[ParetoPoint]:
    """Find Pareto-optimal configs across specified objective axes.

    Default axes: mistake_f1 vs workload_efficiency (precision vs editorial burden).
    """
    axes = objective_axes or ["mistake_f1", "workload_efficiency"]
    return _find_pareto_frontier(sweep.results, ObjectiveWeights(), axes)


def check_early_stopping(
    convergence_history: list[tuple[int, float]],
    patience: int = 200,
    min_improvement: float = 0.001,
    window: int = 100,
) -> tuple[bool, str]:
    """Check if optimization should stop early.

    Args:
        convergence_history: List of (iteration, best_score) tuples.
        patience: Stop if no improvement in this many iterations.
        min_improvement: Minimum improvement to count as progress.
        window: Look at improvement over this many iterations.

    Returns:
        (should_stop, reason)
    """
    if len(convergence_history) < 2:
        return False, ""

    # Check patience: no improvement in last N entries
    if len(convergence_history) >= patience // 100:
        recent = convergence_history[-(patience // 100):]
        if len(recent) >= 2:
            improvement = recent[-1][1] - recent[0][1]
            if improvement < min_improvement:
                return True, f"No improvement ({improvement:.6f}) in last {patience} iterations"

    # Check convergence rate over window
    if len(convergence_history) >= window // 100 + 1:
        windowed = convergence_history[-(window // 100 + 1):]
        if len(windowed) >= 2:
            rate = (windowed[-1][1] - windowed[0][1]) / max(1, windowed[-1][0] - windowed[0][0])
            if abs(rate) < min_improvement / window:
                return True, f"Convergence rate too low ({rate:.8f}/iter)"

    return False, ""


# ---------------------------------------------------------------------------
# Ablation analysis
# ---------------------------------------------------------------------------

def ablation_analysis(
    base_result: SimulationResult,
    ablation_results: dict[str, SimulationResult],
) -> list[dict[str, Any]]:
    """Analyze impact of removing each detector.

    Args:
        base_result: Result with all detectors enabled.
        ablation_results: Map of detector_name → result with that detector disabled.

    Returns:
        List of {detector, base_score, ablated_score, delta, impact} sorted by impact.
    """
    base_score = base_result.combined_score
    impacts = []

    for detector_name, ablated in ablation_results.items():
        ablated_score = ablated.combined_score
        delta = base_score - ablated_score

        impacts.append({
            "detector": detector_name,
            "base_score": round(base_score, 4),
            "ablated_score": round(ablated_score, 4),
            "delta": round(delta, 4),
            "impact": "positive" if delta > 0.01 else ("negative" if delta < -0.01 else "neutral"),
            "mistake_f1_delta": round(
                base_result.metrics.get("mistake_f1", 0) - ablated.metrics.get("mistake_f1", 0), 4
            ),
            "pickup_f1_delta": round(
                base_result.metrics.get("pickup_f1", 0) - ablated.metrics.get("pickup_f1", 0), 4
            ),
        })

    return sorted(impacts, key=lambda x: abs(x["delta"]), reverse=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _weighted_objective(metrics: dict[str, Any], weights: ObjectiveWeights) -> float:
    """Compute weighted objective from metrics dict."""
    mistake = metrics.get("mistake", {})
    pickup = metrics.get("pickup", {})
    ranking = metrics.get("ranking", {})
    splice = metrics.get("splice", {})
    workload = metrics.get("workload", {})

    components = {
        "mistake_f1": mistake.get("f1", metrics.get("mistake_f1", 0.0)),
        "pickup_f1": pickup.get("f1", metrics.get("pickup_f1", 0.0)),
        "ranking_top1": ranking.get("top1_accuracy", 0.0),
        "splice_accuracy": splice.get("accuracy", 0.0),
        "workload_efficiency": 1.0 - workload.get("flag_rate", 0.5),
        "priority_accuracy": metrics.get("priority_accuracy", 0.0),
        "action_accuracy": metrics.get("action_accuracy", 0.0),
    }

    w = weights.to_dict()
    score = sum(components.get(k, 0.0) * v for k, v in w.items())
    total_weight = sum(w.values())
    return score / total_weight if total_weight > 0 else 0.0


def _find_pareto_frontier(
    results: list[SimulationResult],
    weights: ObjectiveWeights,
    axes: list[str] | None = None,
) -> list[ParetoPoint]:
    """Find Pareto-optimal points from simulation results."""
    default_axes = ["mistake_f1", "pickup_f1", "workload_efficiency"]
    axes = axes or default_axes

    # Build points with objective values
    points: list[ParetoPoint] = []
    for r in results:
        objectives = _extract_objectives(r.metrics, axes)
        points.append(ParetoPoint(
            config=r.config,
            metrics=r.metrics,
            objectives=objectives,
            combined_score=_weighted_objective(r.metrics, weights),
        ))

    # Filter dominated points
    frontier: list[ParetoPoint] = []
    for candidate in points:
        dominated = False
        for other in points:
            if other is candidate:
                continue
            if other.dominates(candidate):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)

    return sorted(frontier, key=lambda p: p.combined_score, reverse=True)


def _extract_objectives(metrics: dict[str, Any], axes: list[str]) -> dict[str, float]:
    """Extract objective values from metrics dict."""
    mistake = metrics.get("mistake", {})
    pickup = metrics.get("pickup", {})
    ranking = metrics.get("ranking", {})
    workload = metrics.get("workload", {})

    lookup = {
        "mistake_f1": mistake.get("f1", metrics.get("mistake_f1", 0.0)),
        "mistake_precision": mistake.get("precision", 0.0),
        "mistake_recall": mistake.get("recall", 0.0),
        "pickup_f1": pickup.get("f1", metrics.get("pickup_f1", 0.0)),
        "ranking_top1": ranking.get("top1_accuracy", 0.0),
        "workload_efficiency": 1.0 - workload.get("flag_rate", 0.5),
        "priority_accuracy": metrics.get("priority_accuracy", 0.0),
    }

    return {axis: lookup.get(axis, 0.0) for axis in axes}
