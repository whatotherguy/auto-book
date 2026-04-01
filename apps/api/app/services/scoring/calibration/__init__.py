"""Blitz Calibration Harness — offline simulation, evaluation, and optimization framework.

Quick start:
    from app.services.scoring.calibration import BlitzHarness

    harness = BlitzHarness()
    harness.generate_synthetic_dataset(n_per_type=20)
    result = harness.run_blitz(strategy="monte_carlo", n_configs=500)
    print(result.report)
    harness.export(Path("./calibration_output"))
"""

from .config import ScoringConfig, ConfigStore, default_config, config_from_weights
from .dataset import (
    CalibrationDataset,
    LabeledSegment,
    GroundTruth,
    AltTakeGroup,
    make_clean_segment,
)
from .harness import BlitzHarness, BlitzResult
from .metrics import (
    EvaluationResult,
    ClassificationMetrics,
    RankingMetrics,
    WorkloadMetrics,
    evaluate_predictions,
    evaluate_full,
)
from .optimizer import ObjectiveWeights, OptimizationResult
from .perturbations import (
    PerturbationSpec,
    apply_perturbation,
    generate_synthetic_dataset,
)
from .simulation import SweepResult, SimulationResult, run_calibration_sweep

__all__ = [
    # Harness
    "BlitzHarness",
    "BlitzResult",
    # Config
    "ScoringConfig",
    "ConfigStore",
    "default_config",
    "config_from_weights",
    # Dataset
    "CalibrationDataset",
    "LabeledSegment",
    "GroundTruth",
    "AltTakeGroup",
    "make_clean_segment",
    # Metrics
    "EvaluationResult",
    "ClassificationMetrics",
    "RankingMetrics",
    "WorkloadMetrics",
    "evaluate_predictions",
    "evaluate_full",
    # Optimizer
    "ObjectiveWeights",
    "OptimizationResult",
    # Perturbations
    "PerturbationSpec",
    "apply_perturbation",
    "generate_synthetic_dataset",
    # Simulation
    "SweepResult",
    "SimulationResult",
    "run_calibration_sweep",
]
