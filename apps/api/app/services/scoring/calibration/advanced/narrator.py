"""Per-narrator calibration: separate configs per narrator with adaptive baselines."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ..config import ScoringConfig
from ..dataset import CalibrationDataset
from ..harness import BlitzHarness, BlitzResult
from ..optimizer import ObjectiveWeights


@dataclass
class NarratorProfile:
    """Calibrated scoring profile for a specific narrator."""
    narrator_id: str
    config: ScoringConfig
    baseline_overrides: dict[str, float] = field(default_factory=dict)
    calibration_metrics: dict[str, Any] = field(default_factory=dict)
    segment_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "narrator_id": self.narrator_id,
            "config": self.config.to_dict(),
            "baseline_overrides": self.baseline_overrides,
            "calibration_metrics": self.calibration_metrics,
            "segment_count": self.segment_count,
        }


def calibrate_per_narrator(
    dataset: CalibrationDataset,
    base_config: ScoringConfig | None = None,
    n_configs: int = 200,
    strategy: str = "monte_carlo",
    min_segments: int = 10,
    objective_weights: ObjectiveWeights | None = None,
) -> dict[str, NarratorProfile]:
    """Run calibration separately for each narrator in the dataset.

    Returns a dict of narrator_id → NarratorProfile with tuned configs.
    """
    base = base_config or ScoringConfig()
    profiles: dict[str, NarratorProfile] = {}

    for narrator_id in dataset.narrator_ids:
        narrator_data = dataset.filter_by_narrator(narrator_id)
        if narrator_data.segment_count < min_segments:
            continue

        harness = BlitzHarness(base_config=copy.deepcopy(base))
        harness.set_dataset(narrator_data)
        result = harness.run_blitz(
            strategy=strategy,
            n_configs=n_configs,
            objective_weights=objective_weights,
        )

        if result.best_config:
            profiles[narrator_id] = NarratorProfile(
                narrator_id=narrator_id,
                config=result.best_config,
                calibration_metrics=result.sweep.best_result.metrics if result.sweep.best_result else {},
                segment_count=narrator_data.segment_count,
            )

    return profiles


def select_narrator_config(
    narrator_id: str,
    profiles: dict[str, NarratorProfile],
    fallback_config: ScoringConfig | None = None,
) -> ScoringConfig:
    """Select the best config for a narrator, falling back to default."""
    if narrator_id in profiles:
        return profiles[narrator_id].config
    return fallback_config or ScoringConfig()
