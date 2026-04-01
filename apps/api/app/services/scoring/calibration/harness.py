"""Blitz Calibration Harness: main orchestrator for experiment workflows.

Usage:
    harness = BlitzHarness()
    harness.load_dataset(path) or harness.generate_synthetic_dataset(n=500)
    result = harness.run_blitz(strategy="monte_carlo", n_configs=1000)
    harness.export(output_dir)
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ScoringConfig, ConfigStore, ALL_DETECTOR_NAMES, default_config
from .dataset import (
    CalibrationDataset,
    LabeledSegment,
    make_clean_segment,
)
from .metrics import (
    EvaluationResult,
    evaluate_full,
    evaluate_ranking,
    threshold_sweep,
)
from .optimizer import (
    ObjectiveWeights,
    OptimizationResult,
    ablation_analysis,
    optimize,
)
from .perturbations import (
    PerturbationSpec,
    generate_synthetic_dataset,
    apply_session_drift,
    apply_noise_degradation,
)
from .reporting import (
    export_results,
    generate_report,
    generate_ablation_report,
    generate_confusion_matrix_report,
)
from .scoring_interface import ScoringEngineInterface
from .simulation import (
    SweepResult,
    generate_grid_configs,
    generate_latin_hypercube_configs,
    generate_monte_carlo_configs,
    run_simulation,
    run_sweep,
)

logger = logging.getLogger(__name__)


@dataclass
class BlitzResult:
    """Complete result from a blitz calibration run."""
    sweep: SweepResult
    optimization: OptimizationResult
    ablation: list[dict[str, Any]] = field(default_factory=list)
    report: str = ""
    dataset_summary: dict[str, Any] = field(default_factory=dict)
    elapsed_total_ms: float = 0.0

    @property
    def best_config(self) -> ScoringConfig | None:
        return self.optimization.best_config()

    @property
    def best_score(self) -> float:
        if self.sweep.best_result:
            return self.sweep.best_result.combined_score
        return 0.0


class BlitzHarness:
    """Main orchestrator for blitz calibration experiments.

    Workflow:
        1. Load or generate dataset
        2. Configure search strategy
        3. Run simulation sweep
        4. Optimize and analyze
        5. Export results
    """

    def __init__(
        self,
        base_config: ScoringConfig | None = None,
        config_store_dir: Path | None = None,
    ) -> None:
        self.base_config = base_config or default_config()
        self.dataset: CalibrationDataset | None = None
        self.baseline: dict[str, Any] | None = None
        self.engine = ScoringEngineInterface(self.base_config)
        self.config_store = ConfigStore(config_store_dir) if config_store_dir else None
        self._last_result: BlitzResult | None = None

    # ------------------------------------------------------------------
    # Dataset management
    # ------------------------------------------------------------------

    def load_dataset(self, path: Path) -> CalibrationDataset:
        """Load a labeled dataset from disk."""
        self.dataset = CalibrationDataset.load(path)
        self._rebuild_baseline()
        logger.info("Loaded dataset: %s", self.dataset.summary())
        return self.dataset

    def set_dataset(self, dataset: CalibrationDataset) -> None:
        """Set a pre-built dataset."""
        self.dataset = dataset
        self._rebuild_baseline()

    def generate_synthetic_dataset(
        self,
        n_per_type: int = 20,
        n_clean: int = 30,
        seed: int = 42,
        narrator_ids: list[str] | None = None,
    ) -> CalibrationDataset:
        """Generate a synthetic calibration dataset."""
        # Build clean base features
        base_features = []
        for i in range(n_clean):
            seg = make_clean_segment(
                segment_id=f"base_{i}",
                narrator_id=(narrator_ids or ["default"])[i % len(narrator_ids or ["default"])],
                speech_rate_wps=2.5 + (i % 5) * 0.3,
                rms_db=-22.0 + (i % 4) * 1.0,
                f0_mean_hz=130.0 + (i % 6) * 10.0,
                f0_std_hz=18.0 + (i % 5) * 3.0,
            )
            base_features.append(seg.features)

        segments = generate_synthetic_dataset(
            base_features=base_features,
            n_per_type=n_per_type,
            seed=seed,
        )

        self.dataset = CalibrationDataset(
            name=f"synthetic_{n_per_type}x{len(base_features)}",
            description="Auto-generated synthetic calibration dataset",
            segments=segments,
        )
        self._rebuild_baseline()
        logger.info("Generated synthetic dataset: %s", self.dataset.summary())
        return self.dataset

    # ------------------------------------------------------------------
    # Core blitz run
    # ------------------------------------------------------------------

    def run_blitz(
        self,
        strategy: str = "monte_carlo",
        n_configs: int = 500,
        jitter: float = 0.3,
        seed: int = 42,
        max_workers: int = 1,
        objective_weights: ObjectiveWeights | None = None,
        param_grid: dict[str, list[float]] | None = None,
        param_ranges: dict[str, tuple[float, float]] | None = None,
        run_ablation: bool = False,
    ) -> BlitzResult:
        """Run a full blitz calibration sweep.

        Args:
            strategy: "monte_carlo", "grid", "latin_hypercube"
            n_configs: Number of configurations to evaluate.
            jitter: Jitter factor for Monte Carlo sampling.
            seed: Random seed.
            max_workers: Parallel workers (1 = sequential).
            objective_weights: Custom optimization objective weights.
            param_grid: For grid search — maps param paths to value lists.
            param_ranges: For LHS — maps param paths to (min, max) ranges.
            run_ablation: Whether to run ablation analysis after sweep.

        Returns:
            BlitzResult with sweep, optimization, and report.
        """
        if not self.dataset or not self.dataset.segments:
            raise ValueError("No dataset loaded. Call load_dataset() or generate_synthetic_dataset() first.")

        t0 = time.monotonic()

        # Generate configs
        configs = self._generate_configs(
            strategy, n_configs, jitter, seed, param_grid, param_ranges,
        )

        # Prepare segment dicts
        segment_dicts = [s.to_dict() for s in self.dataset.segments]

        # Run sweep
        sweep = run_sweep(
            configs=configs,
            segments=segment_dicts,
            baseline=self.baseline,
            max_workers=max_workers,
        )

        # Optimize
        optimization = optimize(sweep, objective_weights)

        # Ablation (optional)
        ablation: list[dict[str, Any]] = []
        if run_ablation and sweep.best_result:
            ablation = self._run_ablation(sweep.best_result.config, segment_dicts)

        # Report
        report = generate_report(sweep, optimization)

        result = BlitzResult(
            sweep=sweep,
            optimization=optimization,
            ablation=ablation,
            report=report,
            dataset_summary=self.dataset.summary(),
            elapsed_total_ms=(time.monotonic() - t0) * 1000,
        )

        self._last_result = result
        return result

    # ------------------------------------------------------------------
    # Specialized runs
    # ------------------------------------------------------------------

    def run_ablation_test(self, config: ScoringConfig | None = None) -> list[dict[str, Any]]:
        """Run ablation test: measure impact of removing each detector."""
        if not self.dataset:
            raise ValueError("No dataset loaded.")

        cfg = config or self.base_config
        segment_dicts = [s.to_dict() for s in self.dataset.segments]
        return self._run_ablation(cfg, segment_dicts)

    def run_threshold_sweep(
        self,
        config: ScoringConfig | None = None,
        score_field: str = "mistake_score",
        truth_field: str = "is_mistake",
    ) -> list[dict[str, Any]]:
        """Sweep thresholds to find optimal operating point."""
        if not self.dataset:
            raise ValueError("No dataset loaded.")

        cfg = config or self.base_config
        engine = ScoringEngineInterface(cfg)
        segment_dicts = [s.to_dict() for s in self.dataset.segments]

        predictions = []
        ground_truths = []
        for seg in segment_dicts:
            result = engine.score_segment(seg.get("features", {}), self.baseline or {})
            predictions.append(result.to_prediction(cfg))
            ground_truths.append(seg.get("ground_truth", {}))

        return threshold_sweep(predictions, ground_truths, score_field, truth_field)

    def run_narrator_calibration(
        self,
        strategy: str = "monte_carlo",
        n_configs: int = 200,
        **kwargs: Any,
    ) -> dict[str, BlitzResult]:
        """Run separate calibration per narrator.

        Returns a dict of narrator_id → BlitzResult.
        """
        if not self.dataset:
            raise ValueError("No dataset loaded.")

        results: dict[str, BlitzResult] = {}
        for narrator_id in self.dataset.narrator_ids:
            narrator_dataset = self.dataset.filter_by_narrator(narrator_id)
            if narrator_dataset.segment_count < 10:
                logger.warning("Skipping narrator %s: only %d segments", narrator_id, narrator_dataset.segment_count)
                continue

            harness = BlitzHarness(base_config=copy.deepcopy(self.base_config))
            harness.set_dataset(narrator_dataset)
            results[narrator_id] = harness.run_blitz(
                strategy=strategy, n_configs=n_configs, **kwargs,
            )

        return results

    def run_noise_robustness_test(
        self,
        config: ScoringConfig | None = None,
        noise_levels: list[float] | None = None,
        seed: int = 42,
    ) -> list[dict[str, Any]]:
        """Test a config's robustness across varying recording quality.

        Returns metrics at each noise level.
        """
        if not self.dataset:
            raise ValueError("No dataset loaded.")

        cfg = config or self.base_config
        levels = noise_levels or [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
        results = []

        for level in levels:
            # Apply noise degradation to all segments
            noisy_segments = []
            for seg in self.dataset.segments:
                noisy_feat = apply_noise_degradation(seg.features, level, seed)
                noisy_seg = LabeledSegment(
                    segment_id=seg.segment_id,
                    features=noisy_feat,
                    ground_truth=seg.ground_truth,
                    source=seg.source,
                )
                noisy_segments.append(noisy_seg.to_dict())

            sim_result = run_simulation(cfg, noisy_segments, self.baseline or {})
            results.append({
                "noise_level": level,
                "combined_score": sim_result.combined_score,
                "metrics": sim_result.metrics,
            })

        return results

    def run_drift_test(
        self,
        config: ScoringConfig | None = None,
        n_positions: int = 10,
        drift_intensity: float = 1.0,
        seed: int = 42,
    ) -> list[dict[str, Any]]:
        """Test config robustness across simulated session drift (fatigue).

        Returns metrics at each session position.
        """
        if not self.dataset:
            raise ValueError("No dataset loaded.")

        cfg = config or self.base_config
        results = []

        for i in range(n_positions):
            position = i / max(1, n_positions - 1)
            drifted_segments = []
            for seg in self.dataset.segments:
                drifted_feat = apply_session_drift(seg.features, position, drift_intensity, seed)
                drifted_seg = LabeledSegment(
                    segment_id=seg.segment_id,
                    features=drifted_feat,
                    ground_truth=seg.ground_truth,
                    source=seg.source,
                )
                drifted_segments.append(drifted_seg.to_dict())

            sim_result = run_simulation(cfg, drifted_segments, self.baseline or {})
            results.append({
                "session_position": round(position, 2),
                "combined_score": sim_result.combined_score,
                "metrics": sim_result.metrics,
            })

        return results

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, output_dir: Path) -> dict[str, Path]:
        """Export last run's results to disk."""
        if not self._last_result:
            raise ValueError("No results to export. Run run_blitz() first.")

        paths = export_results(
            self._last_result.sweep,
            self._last_result.optimization,
            output_dir,
        )

        # Also export dataset summary
        summary_path = output_dir / "dataset_summary.json"
        import json
        summary_path.write_text(
            json.dumps(self._last_result.dataset_summary, indent=2),
            encoding="utf-8",
        )
        paths["dataset_summary"] = summary_path

        # Export ablation if available
        if self._last_result.ablation:
            abl_path = output_dir / "ablation.json"
            abl_path.write_text(
                json.dumps(self._last_result.ablation, indent=2),
                encoding="utf-8",
            )
            paths["ablation"] = abl_path

            report = generate_ablation_report(self._last_result.ablation)
            abl_report_path = output_dir / "ablation_report.txt"
            abl_report_path.write_text(report, encoding="utf-8")
            paths["ablation_report"] = abl_report_path

        return paths

    def save_best_config(self, name: str | None = None) -> Path | None:
        """Save the best config from last run to the config store."""
        if not self._last_result or not self._last_result.best_config:
            return None
        if not self.config_store:
            raise ValueError("No config_store_dir configured.")
        return self.config_store.save(self._last_result.best_config, name)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild_baseline(self) -> None:
        """Rebuild chapter baseline from current dataset."""
        if not self.dataset or not self.dataset.segments:
            self.baseline = None
            return
        features = [s.features for s in self.dataset.segments]
        self.baseline = self.engine.build_baseline(features)

    def _generate_configs(
        self,
        strategy: str,
        n_configs: int,
        jitter: float,
        seed: int,
        param_grid: dict[str, list[float]] | None,
        param_ranges: dict[str, tuple[float, float]] | None,
    ) -> list[ScoringConfig]:
        """Generate configs based on search strategy."""
        if strategy == "grid":
            if not param_grid:
                raise ValueError("param_grid required for grid search strategy")
            return generate_grid_configs(self.base_config, param_grid, max_configs=n_configs)
        elif strategy == "latin_hypercube":
            return generate_latin_hypercube_configs(
                self.base_config, n_configs=n_configs, seed=seed, param_ranges=param_ranges,
            )
        else:  # monte_carlo (default)
            return generate_monte_carlo_configs(
                self.base_config, n_configs=n_configs, jitter=jitter, seed=seed,
            )

    def _run_ablation(
        self,
        config: ScoringConfig,
        segment_dicts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run ablation analysis: disable each detector and measure impact."""
        # Run base
        base_result = run_simulation(config, segment_dicts, self.baseline or {})

        # Run with each detector disabled
        ablation_results: dict[str, Any] = {}
        for detector_name in ALL_DETECTOR_NAMES:
            ablated_config = copy.deepcopy(config)
            ablated_config.detector_toggles[detector_name] = False
            ablated_config.config_hash = ablated_config._compute_hash()

            ablation_results[detector_name] = run_simulation(
                ablated_config, segment_dicts, self.baseline or {},
            )

        return ablation_analysis(base_result, ablation_results)
