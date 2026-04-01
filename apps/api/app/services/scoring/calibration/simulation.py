"""Simulation runner: grid search, Monte Carlo, Latin Hypercube sampling.

Evaluates scoring configurations against labeled datasets in batch.
Supports parallel execution via ProcessPoolExecutor.
"""

from __future__ import annotations

import copy
import itertools
import logging
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from ..baseline import build_chapter_baseline
from ..composite import compute_all_composites
from ..derived_features import compute_derived_features
from ..detector_registry import run_all_detectors
from ..recommendations import generate_recommendation
from .config import ScoringConfig, ALL_DETECTOR_NAMES
from .metrics import evaluate_predictions

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Result of evaluating a single config against a dataset."""
    config: ScoringConfig
    metrics: dict[str, Any]
    predictions: list[dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def combined_score(self) -> float:
        return self.metrics.get("combined_f1", self.metrics.get("combined_score", 0.0))


@dataclass
class SweepResult:
    """Result of a full parameter sweep."""
    results: list[SimulationResult] = field(default_factory=list)
    best_result: SimulationResult | None = None
    convergence_history: list[tuple[int, float]] = field(default_factory=list)
    total_configs: int = 0
    total_elapsed_ms: float = 0.0
    search_strategy: str = ""

    @property
    def sorted_results(self) -> list[SimulationResult]:
        return sorted(self.results, key=lambda r: r.combined_score, reverse=True)

    def top_n(self, n: int = 10) -> list[SimulationResult]:
        return self.sorted_results[:n]


# ---------------------------------------------------------------------------
# Config generation strategies
# ---------------------------------------------------------------------------

def generate_grid_configs(
    base_config: ScoringConfig,
    param_grid: dict[str, list[float]],
    max_configs: int = 10000,
) -> list[ScoringConfig]:
    """Generate configs by grid search over weight parameters.

    param_grid maps weight keys to lists of values to try.
    Example: {"mistake.text_mismatch": [0.2, 0.3, 0.4], "mistake.repeated_phrase": [0.1, 0.2, 0.3]}
    """
    # Parse param_grid into structured mutations
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())

    configs = []
    for combo in itertools.islice(itertools.product(*param_values), max_configs):
        cfg = copy.deepcopy(base_config)
        for name, value in zip(param_names, combo):
            _apply_param(cfg, name, value)
        cfg.config_hash = cfg._compute_hash()
        configs.append(cfg)

    return configs


def generate_monte_carlo_configs(
    base_config: ScoringConfig,
    n_configs: int = 1000,
    jitter: float = 0.3,
    seed: int = 42,
) -> list[ScoringConfig]:
    """Generate configs by Monte Carlo random sampling around base."""
    rng = random.Random(seed)
    configs = []

    for _ in range(n_configs):
        cfg = copy.deepcopy(base_config)

        # Jitter all composite weights
        cfg.mistake_weights = _jitter_weights(cfg.mistake_weights, jitter, rng)
        cfg.pickup_weights = _jitter_weights(cfg.pickup_weights, jitter, rng)
        cfg.performance_weights = _jitter_weights(cfg.performance_weights, jitter, rng)
        cfg.continuity_weights = _jitter_weights(cfg.continuity_weights, jitter, rng)

        # Jitter detector thresholds
        for name in ALL_DETECTOR_NAMES:
            base_t = cfg.detector_thresholds.get(name, 0.3)
            new_t = base_t * (1.0 + rng.uniform(-jitter, jitter))
            cfg.detector_thresholds[name] = max(0.05, min(0.95, new_t))

        # Jitter recommendation thresholds
        rt = cfg.recommendation_thresholds
        rt.mistake_trigger = max(0.1, min(0.9, rt.mistake_trigger + rng.uniform(-0.15, 0.15)))
        rt.pickup_trigger = max(0.1, min(0.9, rt.pickup_trigger + rng.uniform(-0.15, 0.15)))

        cfg.config_hash = cfg._compute_hash()
        configs.append(cfg)

    return configs


def generate_latin_hypercube_configs(
    base_config: ScoringConfig,
    n_configs: int = 200,
    seed: int = 42,
    param_ranges: dict[str, tuple[float, float]] | None = None,
) -> list[ScoringConfig]:
    """Generate configs using Latin Hypercube Sampling for better coverage.

    LHS ensures each parameter dimension is evenly sampled, giving better
    coverage than pure Monte Carlo with fewer samples.
    """
    rng = random.Random(seed)

    # Default ranges for key parameters
    ranges = param_ranges or {
        "mistake.text_mismatch": (0.15, 0.55),
        "mistake.repeated_phrase": (0.05, 0.40),
        "mistake.skipped_text": (0.05, 0.40),
        "pickup.pickup_pattern": (0.15, 0.55),
        "pickup.restart_gap": (0.10, 0.45),
        "pickup.click_transient": (0.05, 0.30),
        "threshold.global": (0.15, 0.50),
        "rec.mistake_trigger": (0.30, 0.70),
        "rec.pickup_trigger": (0.35, 0.75),
    }

    param_names = list(ranges.keys())
    n_params = len(param_names)

    # Generate LHS samples: for each dimension, create n_configs evenly spaced intervals
    # then shuffle the interval assignments independently per dimension
    samples: list[list[float]] = []
    for _ in range(n_params):
        intervals = list(range(n_configs))
        rng.shuffle(intervals)
        samples.append(intervals)

    configs = []
    for i in range(n_configs):
        cfg = copy.deepcopy(base_config)

        for j, param_name in enumerate(param_names):
            lo, hi = ranges[param_name]
            # Map interval to value within range
            interval = samples[j][i]
            uniform_sample = (interval + rng.random()) / n_configs
            value = lo + uniform_sample * (hi - lo)

            _apply_param(cfg, param_name, value)

        # Normalize weights to sum to 1
        _normalize_weights(cfg)
        cfg.config_hash = cfg._compute_hash()
        configs.append(cfg)

    return configs


# ---------------------------------------------------------------------------
# Simulation execution
# ---------------------------------------------------------------------------

def run_simulation(
    config: ScoringConfig,
    segments: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> SimulationResult:
    """Score all segments with a config and evaluate against ground truth."""
    t0 = time.monotonic()

    predictions = []
    ground_truths = []

    for segment in segments:
        features = segment.get("features", {})
        gt = segment.get("ground_truth", {})

        derived = compute_derived_features(features, baseline)
        detector_outputs = run_all_detectors(features, derived, config.detector_configs)
        composites = compute_all_composites(detector_outputs, config.composite_weights)
        recommendation = generate_recommendation(composites)

        thresh = config.recommendation_thresholds
        pred = {
            "is_mistake": composites.get("mistake_candidate", {}).get("score", 0) > thresh.mistake_trigger,
            "is_pickup": composites.get("pickup_candidate", {}).get("score", 0) > thresh.pickup_trigger,
            "priority": recommendation.get("priority", "info"),
            "action": recommendation.get("action", "no_action"),
            "needs_review": recommendation.get("action", "no_action") not in ("no_action", "safe_auto_cut"),
            "safe_to_auto_cut": composites.get("splice_readiness", {}).get("score", 0) > thresh.splice_trigger,
            "mistake_score": composites.get("mistake_candidate", {}).get("score", 0),
            "pickup_score": composites.get("pickup_candidate", {}).get("score", 0),
            "performance_score": composites.get("performance_quality", {}).get("score", 0),
            "splice_score": composites.get("splice_readiness", {}).get("score", 0),
        }
        predictions.append(pred)
        ground_truths.append(gt)

    metrics = evaluate_predictions(predictions, ground_truths)
    elapsed = (time.monotonic() - t0) * 1000

    return SimulationResult(
        config=config,
        metrics=metrics,
        predictions=predictions,
        elapsed_ms=elapsed,
    )


def run_sweep(
    configs: list[ScoringConfig],
    segments: list[dict[str, Any]],
    baseline: dict[str, Any] | None = None,
    max_workers: int = 1,
    progress_interval: int = 100,
) -> SweepResult:
    """Run full parameter sweep — sequential or parallel.

    Args:
        configs: List of configs to evaluate.
        segments: Labeled segment dicts (features + ground_truth).
        baseline: Shared baseline. Built from segments if None.
        max_workers: Number of parallel workers (1 = sequential).
        progress_interval: Log progress every N configs.
    """
    t0 = time.monotonic()

    if baseline is None:
        dummy_issues = [{"prosody_features_json": "{}", "audio_features_json": "{}"} for _ in segments]
        baseline = build_chapter_baseline(dummy_issues, [], [])

    sweep = SweepResult(
        total_configs=len(configs),
        search_strategy="parallel" if max_workers > 1 else "sequential",
    )
    best_score = -1.0

    if max_workers <= 1:
        # Sequential execution
        for i, config in enumerate(configs):
            result = run_simulation(config, segments, baseline)
            sweep.results.append(result)

            if result.combined_score > best_score:
                best_score = result.combined_score
                sweep.best_result = result

            if (i + 1) % progress_interval == 0:
                sweep.convergence_history.append((i + 1, best_score))
                logger.debug("Sweep %d/%d: best=%.4f", i + 1, len(configs), best_score)
    else:
        # Parallel execution
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_simulation, config, segments, baseline): i
                for i, config in enumerate(configs)
            }
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                sweep.results.append(result)
                completed += 1

                if result.combined_score > best_score:
                    best_score = result.combined_score
                    sweep.best_result = result

                if completed % progress_interval == 0:
                    sweep.convergence_history.append((completed, best_score))
                    logger.debug("Sweep %d/%d: best=%.4f", completed, len(configs), best_score)

    sweep.convergence_history.append((len(configs), best_score))
    sweep.total_elapsed_ms = (time.monotonic() - t0) * 1000

    return sweep


def run_calibration_sweep(
    labeled_segments: list[dict[str, Any]],
    iterations: int = 1000,
    jitter: float = 0.3,
) -> dict[str, Any]:
    """Legacy-compatible Monte Carlo sweep. Wraps new infrastructure.

    Returns dict with best_config, best_metrics, convergence_history for
    backward compatibility with existing callers.
    """
    if not labeled_segments:
        return {"best_config": None, "best_metrics": None, "convergence_history": []}

    base = ScoringConfig()
    configs = generate_monte_carlo_configs(base, n_configs=iterations, jitter=jitter)

    dummy_issues = [{"prosody_features_json": "{}", "audio_features_json": "{}"} for _ in labeled_segments]
    baseline = build_chapter_baseline(dummy_issues, [], [])

    sweep = run_sweep(configs, labeled_segments, baseline, max_workers=1)

    if sweep.best_result:
        return {
            "best_config": sweep.best_result.config.composite_weights,
            "best_metrics": sweep.best_result.metrics,
            "convergence_history": sweep.convergence_history,
            "iterations": iterations,
        }

    return {"best_config": None, "best_metrics": None, "convergence_history": []}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jitter_weights(weights: dict[str, float], jitter: float, rng: random.Random) -> dict[str, float]:
    """Sample random weights around template, normalize to sum to 1."""
    sampled = {}
    for key, base_val in weights.items():
        sign = 1 if base_val >= 0 else -1
        magnitude = abs(base_val) * (1.0 + rng.uniform(-jitter, jitter))
        sampled[key] = sign * max(0.01, magnitude)

    positive = {k: v for k, v in sampled.items() if v > 0}
    negative = {k: v for k, v in sampled.items() if v < 0}
    pos_sum = sum(positive.values()) or 1.0
    neg_sum = abs(sum(negative.values())) or 1.0

    normalized = {}
    for k, v in positive.items():
        normalized[k] = v / pos_sum
    for k, v in negative.items():
        normalized[k] = v / neg_sum
    return normalized


def _apply_param(cfg: ScoringConfig, param_path: str, value: float) -> None:
    """Apply a parameter value to a config using dot-notation path.

    Paths:
        mistake.text_mismatch → cfg.mistake_weights["text_mismatch"]
        pickup.restart_gap → cfg.pickup_weights["restart_gap"]
        threshold.global → all detector thresholds
        threshold.text_mismatch → cfg.detector_thresholds["text_mismatch"]
        rec.mistake_trigger → cfg.recommendation_thresholds.mistake_trigger
    """
    parts = param_path.split(".", 1)
    if len(parts) != 2:
        return

    category, key = parts

    weight_map = {
        "mistake": "mistake_weights",
        "pickup": "pickup_weights",
        "performance": "performance_weights",
        "continuity": "continuity_weights",
        "take": "take_preference_weights",
    }

    if category in weight_map:
        weights = getattr(cfg, weight_map[category])
        if key in weights:
            weights[key] = value
    elif category == "threshold":
        if key == "global":
            for name in ALL_DETECTOR_NAMES:
                cfg.detector_thresholds[name] = value
        elif key in cfg.detector_thresholds:
            cfg.detector_thresholds[key] = value
    elif category == "rec":
        if hasattr(cfg.recommendation_thresholds, key):
            setattr(cfg.recommendation_thresholds, key, value)


def _normalize_weights(cfg: ScoringConfig) -> None:
    """Normalize all weight dicts so positive weights sum to 1, negative sum to -1."""
    for attr in ["mistake_weights", "pickup_weights", "performance_weights",
                 "continuity_weights", "take_preference_weights"]:
        weights = getattr(cfg, attr)
        positive = {k: v for k, v in weights.items() if v > 0}
        negative = {k: v for k, v in weights.items() if v < 0}

        pos_sum = sum(positive.values()) or 1.0
        neg_sum = abs(sum(negative.values())) or 1.0

        for k, v in positive.items():
            weights[k] = v / pos_sum
        for k, v in negative.items():
            weights[k] = v / neg_sum
