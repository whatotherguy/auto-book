# Blitz Calibration Harness — Architecture & Design Document

## System Overview

The Blitz Calibration Harness is an **offline simulation, evaluation, and optimization framework** for tuning the audiobook editor's heuristic scoring system. It operates entirely on extracted features (no audio I/O required), enabling rapid iteration over thousands of scoring configurations.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BLITZ CALIBRATION HARNESS                        │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │ Dataset   │  │ Perturbation │  │  Scoring    │  │  Config    │  │
│  │ Layer     │──│ Engine       │──│  Engine     │──│  Manager   │  │
│  │           │  │              │  │  Interface  │  │            │  │
│  └─────┬────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘  │
│        │               │                 │               │         │
│        └───────────────┼─────────────────┘               │         │
│                        ▼                                 │         │
│              ┌──────────────────┐                        │         │
│              │  Simulation      │◄───────────────────────┘         │
│              │  Runner          │                                   │
│              └────────┬─────────┘                                   │
│                       │                                             │
│              ┌────────▼─────────┐  ┌──────────────┐                │
│              │  Evaluation      │──│  Optimizer    │                │
│              │  Metrics         │  │  (Pareto)     │                │
│              └────────┬─────────┘  └──────┬───────┘                │
│                       │                    │                        │
│              ┌────────▼────────────────────▼───────┐               │
│              │         Reporting &                  │               │
│              │         Visualization                │               │
│              └─────────────────────────────────────┘               │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ Advanced: Per-Narrator │ Session Drift │ Ablation │ Noise    │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### 1. Configuration Management (`config.py`)

**Purpose**: Version, serialize, store, and rollback scoring configurations.

```
ScoringConfig
├── version: str (semver)
├── created_at: ISO timestamp
├── parent_version: str | None (rollback chain)
├── metadata: dict (narrator, session, notes)
├── weights: CompositeWeights
│   ├── mistake: {detector_name: float}
│   ├── pickup: {detector_name: float}
│   ├── performance: {detector_name: float}
│   ├── continuity: {detector_name: float}
│   └── take_preference: {component: float}
├── thresholds: DetectorThresholds
│   └── {detector_name: float}  (15 entries, default 0.3)
├── detector_toggles: {detector_name: bool}  (15 entries)
├── recommendation_thresholds: RecommendationThresholds
│   ├── mistake_trigger: float (default 0.5)
│   ├── pickup_trigger: float (default 0.6)
│   ├── splice_trigger: float (default 0.8)
│   ├── splice_confidence_min: float (default 0.7)
│   └── performance_trigger: float (default 0.5)
└── normalization: NormalizationSettings
    ├── strategy: "sum_to_one" | "max_normalize" | "raw"
    └── baseline_blend_ratio: float
```

**Key operations**: `save()`, `load()`, `diff(other)`, `rollback()`, `to_production_format()`

### 2. Dataset Layer (`dataset.py`)

Extends existing `labels.py` with richer schemas.

**Labeled Segment Schema**:
```json
{
  "segment_id": "ch3_seg_042",
  "source": "real|synthetic",
  "narrator_id": "narrator_jane",
  "session_id": "session_2024_03_15",
  "features": { /* RawFeatureCatalog */ },
  "derived_features": { /* z-scores, deltas */ },
  "detector_outputs": { /* 15 DetectorOutput dicts */ },
  "ground_truth": {
    "is_mistake": true,
    "is_pickup": false,
    "needs_review": true,
    "safe_to_auto_cut": false,
    "preferred_action": "review_mistake",
    "priority": "high",
    "mistake_type": "text_mismatch|repetition|skipped|none",
    "annotator": "human|synthetic",
    "notes": ""
  }
}
```

**Alt-Take Comparison Schema**:
```json
{
  "group_id": "alt_group_017",
  "manuscript_text": "The rain fell softly on the garden",
  "takes": [
    {
      "take_id": "take_a",
      "segment_id": "ch3_seg_042",
      "features": { },
      "composite_scores": { }
    }
  ],
  "ground_truth": {
    "chosen_take_id": "take_b",
    "ranking": ["take_b", "take_a", "take_c"],
    "annotator": "human",
    "reason": "better_pacing"
  }
}
```

**Dataset operations**: `split(train/val/test)`, `stratify_by(field)`, `filter_by_narrator()`, `augment_with_perturbations()`

### 3. Synthetic Perturbation Engine (`perturbations.py`)

Replaces the basic 5-type engine with 8 parameterized, seeded perturbation types.

| Type | Parameters | Feature Mutations |
|------|-----------|-------------------|
| `click_injection` | position, intensity, duration_ms | has_click_marker, click_confidence, crest_factor, zcr |
| `silence_expansion` | factor (1.5-5x), position | pause_before_ms, has_silence_gap, silence_gap_ms |
| `silence_compression` | factor (0.1-0.5x) | pause_before_ms, pause_after_ms |
| `repeated_phrase` | n_repeats, span_words | spoken_text, issue_type, confidence |
| `restart_simulation` | gap_ms, has_click | issue_type, has_silence_gap, restart_pattern, pause_before_ms |
| `pacing_change` | rate_factor (0.5-2.0) | speech_rate_wps, z_speech_rate, duration_ms |
| `gain_shift` | db_delta (-12 to +6) | rms_db, crest_factor |
| `clipping_simulation` | severity (0.0-1.0) | rms_db, crest_factor, has_onset_burst |

Each perturbation: `Perturbation(type, params, seed) → mutated_features + ground_truth_labels`

### 4. Scoring Engine Interface (`scoring_interface.py`)

Clean adapter between the harness and the existing scoring pipeline.

```python
class ScoringEngineInterface:
    def score_segment(config: ScoringConfig, features: dict, baseline: dict) -> ScoringResult
    def score_batch(config: ScoringConfig, segments: list, baseline: dict) -> list[ScoringResult]
    def score_alt_take_group(config: ScoringConfig, group: AltTakeGroup) -> RankedResult
```

Injects: weights, thresholds, detector toggles, normalization strategy.

### 5. Simulation Runner (`simulation.py`)

**Search strategies**:
- **Grid search**: Enumerate all combinations of discretized parameter ranges
- **Monte Carlo**: Random sampling with jitter around templates
- **Latin Hypercube**: Space-filling random sampling for better coverage
- **Bayesian-inspired**: Use top-N results to narrow search region

**Execution model**:
- `concurrent.futures.ProcessPoolExecutor` for CPU parallelism
- Batch segments into chunks for cache locality
- Cache baseline computation (shared across configs)

### 6. Evaluation Metrics (`metrics.py`)

Extends the basic F1 system:

| Metric | Formula | Purpose |
|--------|---------|---------|
| mistake_precision | TP / (TP + FP) | False positive rate for mistakes |
| mistake_recall | TP / (TP + FN) | Catch rate for real mistakes |
| mistake_f1 | harmonic mean | Balance |
| pickup_precision | same | Pickup false positives |
| pickup_recall | same | Pickup catch rate |
| pickup_f1 | same | Balance |
| splice_safety_accuracy | correct_safe / total_safe | Auto-cut reliability |
| take_ranking_kendall_tau | Kendall τ | Alt-take ranking correlation |
| take_top1_accuracy | correct_top / total_groups | Best-take selection |
| review_workload | flagged / total | Segments needing human review |
| workload_per_hour | flagged / (total_duration_ms / 3600000) | Editorial burden |
| priority_accuracy | exact_match / total | Priority classification |
| action_accuracy | exact_match / total | Recommendation accuracy |
| combined_score | weighted sum | Single optimization target |

### 7. Optimizer (`optimizer.py`)

**Weighted objective function**:
```
objective = (
    mistake_f1 * 0.25 +
    pickup_f1 * 0.20 +
    take_top1_accuracy * 0.15 +
    splice_safety * 0.10 +
    (1 - review_workload) * 0.15 +  # lower workload = better
    priority_accuracy * 0.15
)
```

**Multi-objective optimization**:
- Explore Pareto frontier between precision vs workload
- No single "best" — present tradeoff options
- Configurable objective weights per use case

**Early stopping**:
- Stop if best score hasn't improved in N iterations
- Stop if improvement rate < epsilon over window

### 8. Reporting (`reporting.py`)

Text-based reports (no matplotlib dependency required):
- Score distribution histograms (ASCII)
- Confusion matrices (text table)
- Top-N configurations ranked by objective
- Per-detector sensitivity analysis
- Workload vs accuracy tradeoff table
- Convergence history
- JSON export for external visualization

### 9. Experiment Harness (`harness.py`)

Orchestrates the full workflow:

```
1. Load/create dataset
2. (Optional) Generate perturbations
3. Build search space (grid/monte carlo/latin hypercube)
4. Run simulation batch across configs
5. Evaluate metrics for each config
6. Optimize: rank, find Pareto frontier
7. Generate report
8. Export best configs
```

### 10. Advanced Features

- **Per-Narrator Calibration**: Separate config per narrator_id, adaptive baselines
- **Session Drift**: Simulate fatigue by progressively degrading features
- **Noise Robustness**: Test configs under varying recording quality
- **Ablation Testing**: Measure impact of removing each detector individually

---

## Performance Design

| Concern | Solution |
|---------|----------|
| CPU parallelism | ProcessPoolExecutor with configurable workers |
| Feature caching | Baseline computed once, shared across configs |
| Memory | Streaming evaluation — don't hold all results in RAM |
| Batching | Segments processed in configurable batch sizes |
| Early exit | Skip remaining configs if Pareto-dominated |

---

## Data Flow

```
Dataset (JSON files)
    │
    ├── Real labeled segments (human-annotated)
    ├── Synthetic segments (perturbation engine)
    │
    ▼
Scoring Engine Interface
    │ (receives ScoringConfig per run)
    │
    ├── compute_derived_features(features, baseline)
    ├── run_all_detectors(features, derived, detector_configs)
    ├── compute_all_composites(outputs, weights)
    ├── generate_recommendation(composites, thresholds)
    │
    ▼
ScoringResult per segment
    │
    ▼
Evaluation Metrics (compare vs ground_truth)
    │
    ▼
Optimizer (rank configs, find Pareto frontier)
    │
    ▼
Report + Best Configs (JSON export)
```

---

## File Structure

```
apps/api/app/services/scoring/calibration/
├── __init__.py
├── config.py          # ScoringConfig, versioning, serialization
├── dataset.py         # Enhanced dataset layer, splitting, validation
├── perturbations.py   # 8 perturbation types (UPGRADED)
├── scoring_interface.py  # Adapter to scoring pipeline
├── simulation.py      # Simulation runner (UPGRADED)
├── metrics.py         # Comprehensive metrics (UPGRADED)
├── optimizer.py       # Multi-objective optimizer, Pareto frontier
├── reporting.py       # Text reports, JSON export
├── harness.py         # Main orchestrator
├── labels.py          # (EXISTING) label utilities
└── advanced/
    ├── __init__.py
    ├── narrator.py    # Per-narrator calibration
    ├── drift.py       # Session drift simulation
    ├── noise.py       # Noise robustness testing
    └── ablation.py    # Detector ablation testing

apps/api/tests/
├── test_blitz_config.py
├── test_blitz_dataset.py
├── test_blitz_perturbations.py
├── test_blitz_simulation.py
├── test_blitz_metrics.py
├── test_blitz_optimizer.py
├── test_blitz_harness.py
└── test_blitz_advanced.py
```
