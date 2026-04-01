# Blitz Calibration Runner

You are an expert in running calibration experiments using the Blitz Calibration Harness to tune the audiobook editor's heuristic scoring system. You help users design experiments, interpret results, and deploy optimized configurations.

## When To Use This Skill

Use when you need to:
- Tune scoring weights and thresholds for better accuracy
- Evaluate current scoring performance against labeled data
- Run ablation tests to understand detector importance
- Calibrate per-narrator scoring profiles
- Test scoring robustness against noise or session drift
- Compare two scoring configurations
- Deploy an optimized config to production

## System Context

### Scoring System Parameters (50+ tunable values)

**Composite Weights** (4 weight dicts, ~25 values):
- `mistake_weights`: text_mismatch(0.35), repeated_phrase(0.20), skipped_text(0.20), abnormal_pause(0.10), rushed_delivery(0.05), clipping(0.05), click_transient(0.05)
- `pickup_weights`: pickup_pattern(0.35), restart_gap(0.25), click_transient(0.15), repeated_phrase(0.10), abnormal_pause(0.10), punch_in_boundary(0.05)
- `performance_weights`: flat_delivery(-0.30), weak_landing(-0.20), cadence_drift(-0.15), rushed_delivery(-0.15), clipping(-0.10), room_tone_shift(-0.10)
- `continuity_weights`: continuity_mismatch(-0.40), room_tone_shift(-0.25), punch_in_boundary(-0.20), cadence_drift(-0.15)

**Detector Thresholds** (15 values, default 0.3 each):
- All 15 detectors have individual trigger thresholds

**Recommendation Thresholds** (5 values):
- mistake_trigger(0.5), pickup_trigger(0.6), splice_trigger(0.8), splice_confidence_min(0.7), performance_trigger(0.5)

### Blitz Harness Location
```
apps/api/app/services/scoring/calibration/
```

### Key Imports
```python
from app.services.scoring.calibration import (
    BlitzHarness,
    ScoringConfig,
    ObjectiveWeights,
    CalibrationDataset,
)
```

## Calibration Workflow

### Phase 1: Prepare Dataset

Before calibrating, you need labeled data. Choose one approach:

**Option A: Synthetic dataset (cold start, no real labels)**
```python
harness = BlitzHarness()
dataset = harness.generate_synthetic_dataset(
    n_per_type=20,    # 20 segments per perturbation type
    n_clean=30,       # 30 clean segments
    seed=42,          # reproducible
)
# Result: ~210 segments (30 clean + 9 types * 20)
```

**Option B: Load real labeled data**
```python
from pathlib import Path
harness = BlitzHarness()
dataset = harness.load_dataset(Path("data/calibration/labeled_v1.json"))
```

**Option C: Mix real + synthetic**
```python
harness = BlitzHarness()
real = CalibrationDataset.load(Path("data/calibration/real_labels.json"))
synthetic_harness = BlitzHarness()
synthetic = synthetic_harness.generate_synthetic_dataset(n_per_type=15)
harness.set_dataset(real.merge(CalibrationDataset(segments=synthetic.segments)))
```

**Check dataset balance**:
```python
print(harness.dataset.summary())
# Expected: mistakes > 10%, pickups > 5%, clean > 40%
```

### Phase 2: Choose Calibration Strategy

**Monte Carlo (recommended for initial calibration)**
- Best for: wide exploration, finding good regions
- Speed: fast per iteration, needs more iterations
- Use when: you don't know which parameters matter

```python
result = harness.run_blitz(
    strategy="monte_carlo",
    n_configs=1000,      # 1000 random configurations
    jitter=0.3,          # 30% random variation around defaults
    seed=42,
)
```

**Grid Search (for focused tuning)**
- Best for: tuning specific parameters you've identified as sensitive
- Speed: exponential in number of parameters
- Use when: ablation told you which 2-3 params matter most

```python
result = harness.run_blitz(
    strategy="grid",
    param_grid={
        "mistake.text_mismatch": [0.25, 0.30, 0.35, 0.40, 0.45],
        "mistake.repeated_phrase": [0.10, 0.15, 0.20, 0.25, 0.30],
        "rec.mistake_trigger": [0.35, 0.40, 0.45, 0.50, 0.55],
    },
)
```

**Latin Hypercube (best coverage per sample)**
- Best for: efficient exploration with fewer samples
- Speed: better coverage than Monte Carlo for same budget
- Use when: evaluation is expensive or you want efficiency

```python
result = harness.run_blitz(
    strategy="latin_hypercube",
    n_configs=200,
    param_ranges={
        "mistake.text_mismatch": (0.15, 0.55),
        "pickup.pickup_pattern": (0.15, 0.55),
        "threshold.global": (0.15, 0.50),
        "rec.mistake_trigger": (0.30, 0.70),
    },
)
```

### Phase 3: Choose Optimization Objective

**Balanced (default)** — good for general use:
```python
result = harness.run_blitz(n_configs=500)
```

**High Recall** — catch everything, tolerate more false positives:
```python
result = harness.run_blitz(
    n_configs=500,
    objective_weights=ObjectiveWeights.high_recall(),
)
```

**Low Workload** — minimize editorial burden, accept missing some issues:
```python
result = harness.run_blitz(
    n_configs=500,
    objective_weights=ObjectiveWeights.low_workload(),
)
```

**Custom** — tune to specific needs:
```python
result = harness.run_blitz(
    n_configs=500,
    objective_weights=ObjectiveWeights(
        mistake_f1=0.30,        # Catching mistakes is critical
        pickup_f1=0.15,         # Pickups are less important
        ranking_top1=0.10,      # Alt-take ranking matters
        splice_accuracy=0.05,   # Auto-cut is low priority
        workload_efficiency=0.25, # Keeping workload down matters a lot
        priority_accuracy=0.10,
        action_accuracy=0.05,
    ),
)
```

### Phase 4: Interpret Results

**Read the report**:
```python
print(result.report)
```

The report shows:
1. **Summary** — total configs, elapsed time, best score
2. **Convergence** — whether the search converged (plateau = good)
3. **Top 10 configs** — ranked by combined score
4. **Best config details** — all weights and thresholds
5. **Metrics** — precision, recall, F1, workload for best config

**Key metrics to check**:
- `mistake_f1 > 0.6` — catching real mistakes well
- `pickup_f1 > 0.5` — catching pickups reasonably
- `flag_rate < 0.4` — not flagging too many segments for review
- `priority_accuracy > 0.5` — priorities are meaningful

**Compare with default config**:
```python
from app.services.scoring.calibration.simulation import run_simulation
default_result = run_simulation(ScoringConfig(), segment_dicts, baseline)
print(f"Default: {default_result.combined_score:.4f}")
print(f"Best:    {result.best_score:.4f}")
print(f"Improvement: {result.best_score - default_result.combined_score:+.4f}")
```

### Phase 5: Validate

**Run ablation to understand which detectors matter**:
```python
result = harness.run_blitz(n_configs=500, run_ablation=True)
for entry in result.ablation[:5]:
    print(f"  {entry['detector']:>25s}  delta={entry['delta']:+.4f}  {entry['impact']}")
```

**Run threshold sweep to find optimal operating point**:
```python
curve = harness.run_threshold_sweep(
    config=result.best_config,
    score_field="mistake_score",
    truth_field="is_mistake",
)
for point in curve:
    if point["f1"] > 0:
        print(f"  threshold={point['threshold']:.2f}  P={point['precision']:.3f}  R={point['recall']:.3f}  F1={point['f1']:.3f}")
```

**Test robustness against noise**:
```python
noise_results = harness.run_noise_robustness_test(
    config=result.best_config,
    noise_levels=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
)
for nr in noise_results:
    print(f"  noise={nr['noise_level']:.1f}  score={nr['combined_score']:.4f}")
```

**Test robustness against session drift (fatigue)**:
```python
drift_results = harness.run_drift_test(
    config=result.best_config,
    n_positions=10,
)
for dr in drift_results:
    print(f"  position={dr['session_position']:.1f}  score={dr['combined_score']:.4f}")
```

### Phase 6: Export and Deploy

**Export results to disk**:
```python
paths = harness.export(Path("calibration_output/run_001"))
# Creates: best_config.json, top_configs.json, convergence.json,
#          production_config.json, report.txt, pareto_frontier.json
```

**Save best config for version tracking**:
```python
harness_with_store = BlitzHarness(config_store_dir=Path("calibration_configs"))
# ... run blitz ...
harness_with_store.save_best_config("v1.1_high_recall")
```

**Deploy to production** — update the CalibrationProfile in the database:
```python
production_format = result.best_config.to_production_format()
# Returns: {"weights_json": "...", "thresholds_json": "...", "metrics_json": "..."}
# Use this to create/update a CalibrationProfile record
```

**Compare two configs**:
```python
from app.services.scoring.calibration import ScoringConfig
old_config = ScoringConfig.load(Path("calibration_configs/v1.0.json"))
new_config = result.best_config
diff = old_config.diff(new_config)
for section, changes in diff.items():
    print(f"\n{section}:")
    for key, vals in changes.items():
        print(f"  {key}: {vals['from']:.4f} -> {vals['to']:.4f}")
```

## Advanced Calibration Scenarios

### Per-Narrator Calibration
```python
results = harness.run_narrator_calibration(
    strategy="monte_carlo",
    n_configs=200,
)
for narrator_id, narrator_result in results.items():
    print(f"Narrator {narrator_id}: score={narrator_result.best_score:.4f}")
```

### Iterative Refinement
1. Run wide Monte Carlo sweep (jitter=0.5, n=1000) to find good region
2. Run ablation to identify top 3-5 sensitive parameters
3. Run grid search on those parameters only
4. Validate with threshold sweep and noise robustness

### A/B Comparison of Two Strategies
```python
harness_a = BlitzHarness()
harness_a.set_dataset(dataset)
result_a = harness_a.run_blitz(objective_weights=ObjectiveWeights.balanced())

harness_b = BlitzHarness()
harness_b.set_dataset(dataset)
result_b = harness_b.run_blitz(objective_weights=ObjectiveWeights.high_recall())

print(f"Balanced:    score={result_a.best_score:.4f}")
print(f"High Recall: score={result_b.best_score:.4f}")
```

## Interpreting Metrics

| Metric | Good | Acceptable | Poor | Meaning |
|--------|------|-----------|------|---------|
| mistake_f1 | >0.80 | 0.60-0.80 | <0.60 | Balance of catching vs false-flagging mistakes |
| pickup_f1 | >0.70 | 0.50-0.70 | <0.50 | Pickup/restart detection quality |
| flag_rate | <0.25 | 0.25-0.40 | >0.40 | Editorial workload (lower = less review) |
| priority_accuracy | >0.70 | 0.50-0.70 | <0.50 | Priority labels are meaningful |
| noise drop | <10% | 10-20% | >20% | Score drop at noise_level=0.5 vs 0.0 |

## Troubleshooting

**Score not improving during sweep**:
- Increase n_configs (need more samples)
- Increase jitter (search space too narrow)
- Check dataset balance (need mistakes AND clean segments)

**High false positive rate**:
- Raise recommendation thresholds (mistake_trigger, pickup_trigger)
- Lower detector sensitivity (raise detector thresholds)
- Use ObjectiveWeights.low_workload() to prioritize precision

**Poor recall (missing real issues)**:
- Lower recommendation thresholds
- Increase weights for key detectors (text_mismatch for mistakes)
- Use ObjectiveWeights.high_recall()

**Noise robustness is poor**:
- Raise detector thresholds (less sensitive = more robust)
- Reduce weight on noise-sensitive detectors (click_transient, room_tone_shift)
- Check if whisper_word_confidence features are properly weighted

## Anti-Patterns To Avoid

- Running calibration with fewer than 30 labeled segments (insufficient signal)
- Using only synthetic data for final calibration (validate with real data)
- Optimizing a single metric without checking others (F1 up but workload doubled)
- Deploying without running noise robustness test
- Ignoring the Pareto frontier (sometimes the #2 config has better tradeoffs)
- Re-running calibration without saving the previous config (no rollback possible)
- Setting all detector weights equal (the defaults have meaning from domain analysis)
