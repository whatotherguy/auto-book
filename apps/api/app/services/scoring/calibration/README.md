# calibration

Offline weight-tuning system for the scoring engine — the **Blitz Calibration Harness**.

## Purpose

The primitive detectors use configurable weights and thresholds. The calibration harness runs Monte Carlo sweeps over the weight space to find configurations that best match a hand-labelled ground-truth dataset, then persists the best configuration as a `CalibrationProfile` in the database.

## Files

| File | Description |
|------|-------------|
| `harness.py` | `BlitzHarness` — main orchestrator. Load dataset → run sweep → export best config |
| `config.py` | `ScoringConfig` dataclass; `ConfigStore` for serialisation; `ALL_DETECTOR_NAMES` registry; `default_config()` |
| `dataset.py` | `CalibrationDataset`, `LabeledSegment`, `GroundTruth`; helpers to load labels from disk |
| `labels.py` | JSON label schema helpers; load/validate hand-labelled segment files |
| `simulation.py` | `simulate_scoring()` — run the scoring pipeline against a dataset without touching the database |
| `metrics.py` | `evaluate_full()`, `evaluate_ranking()`, `threshold_sweep()`, `EvaluationResult` |
| `optimizer.py` | `optimize()` (Monte Carlo + grid search), `ablation_analysis()`, `ObjectiveWeights`, `OptimizationResult` |
| `perturbations.py` | `generate_synthetic_dataset()`, `apply_session_drift()` — augment small datasets with realistic perturbations |
| `reporting.py` | Human-readable text reports from `OptimizationResult` |
| `scoring_interface.py` | Thin adapter so calibration code can call the scoring engine without importing pipeline internals |
| [`advanced/`](advanced/) | Narrator-specific profiles and ablation helpers |

## Workflow

```
1. Prepare labelled data
   └─ Place labels.json files in data/calibration/<dataset-name>/

2. Load dataset
   harness.load_dataset(path)         # real hand labels
   harness.generate_synthetic_dataset(n=500)  # or synthetic augmentation

3. Run sweep
   result = harness.run_blitz(strategy="monte_carlo", n_configs=1000)

4. Inspect results
   harness.export(output_dir)         # writes report + best config

5. Promote to database
   POST /calibration/promote  { "profile_id": <id> }
```

## Label format

Labels live in JSON files alongside the audio artifacts. See `labels.py` for the schema. Each entry identifies a segment by chapter/time range and records the expected `GroundTruth` (issue type + severity).
