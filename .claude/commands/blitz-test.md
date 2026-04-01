# Blitz Engine Test Writer

You are an expert in writing tests for the Blitz Calibration Harness — the offline simulation, evaluation, and optimization framework for the audiobook editor's heuristic scoring system.

## When To Use This Skill

Use when you need to:
- Add tests for new or modified blitz engine components
- Validate a new perturbation type
- Test a new metric or evaluation function
- Verify optimizer behavior
- Write integration tests for end-to-end calibration workflows
- Regression test scoring behavior after weight/threshold changes

## System Context

The Blitz Calibration Harness lives at:
```
apps/api/app/services/scoring/calibration/
├── config.py          # ScoringConfig, ConfigStore, versioning
├── dataset.py         # CalibrationDataset, LabeledSegment, GroundTruth
├── perturbations.py   # 8 perturbation types + drift/noise simulation
├── scoring_interface.py  # Adapter to production scoring pipeline
├── simulation.py      # Grid search, Monte Carlo, Latin Hypercube
├── metrics.py         # Precision/recall, ranking, workload, threshold sweeps
├── optimizer.py       # Pareto frontier, objective weighting, early stopping
├── reporting.py       # Text reports, JSON export
├── harness.py         # BlitzHarness orchestrator
└── advanced/
    ├── narrator.py    # Per-narrator calibration
    └── ablation.py    # Single + group ablation testing
```

Existing tests are at:
```
apps/api/tests/test_blitz_*.py
```

The scoring system it calibrates has:
- **15 detectors** across 5 categories (text, timing, audio, prosody, context)
- **5 composite scores**: mistakeCandidate, pickupCandidate, performanceQuality, continuityFit, spliceReadiness
- **Editorial recommendations**: review_mistake, likely_pickup, alt_take_available, safe_auto_cut, manual_review_required, no_action

## Test Writing Workflow

### Step 1: Understand What You're Testing

Read the relevant source module completely before writing tests. Key questions:
- What are the inputs and outputs?
- What are the edge cases (empty inputs, boundary values, zero-division)?
- What should be deterministic/reproducible?
- What invariants must hold?

### Step 2: Choose Test Patterns

Use these patterns based on what you're testing:

**For Config/Data modules** — roundtrip serialization, defaults, validation:
```python
def test_config_roundtrip():
    cfg = ScoringConfig(metadata={"test": True})
    d = cfg.to_dict()
    restored = ScoringConfig.from_dict(d)
    assert restored.config_hash == cfg.config_hash

def test_config_save_load(tmp_path):
    cfg = ScoringConfig()
    path = cfg.save(tmp_path / "config.json")
    loaded = ScoringConfig.load(path)
    assert loaded.config_hash == cfg.config_hash
```

**For Perturbations** — verify feature mutations, reproducibility, input safety:
```python
def test_perturbation_modifies_features():
    feat = make_clean_segment("test").features
    spec = PerturbationSpec(type="click_injection", seed=42)
    result = apply_perturbation(feat, spec)
    assert result["has_click_marker"] is True

def test_perturbation_is_reproducible():
    feat = make_clean_segment("test").features
    spec = PerturbationSpec(type="click_injection", seed=42)
    r1 = apply_perturbation(feat, spec)
    r2 = apply_perturbation(feat, spec)
    assert r1 == r2

def test_perturbation_does_not_mutate_input():
    feat = make_clean_segment("test").features
    original = copy.deepcopy(feat)
    apply_perturbation(feat, PerturbationSpec(type="click_injection", seed=42))
    assert feat == original
```

**For Metrics** — perfect scores, zero scores, edge cases:
```python
def test_perfect_classification():
    cm = ClassificationMetrics(tp=10, fp=0, fn=0, tn=10)
    assert cm.f1 == 1.0

def test_empty_evaluation():
    result = evaluate_predictions([], [])
    assert result["combined_f1"] == 0.0
```

**For Simulation** — config generation counts, uniqueness, sweep completion:
```python
def test_monte_carlo_count():
    configs = generate_monte_carlo_configs(ScoringConfig(), n_configs=50)
    assert len(configs) == 50

def test_sweep_finds_best():
    sweep = run_sweep(configs, segments)
    assert sweep.best_result is not None
```

**For Harness (integration)** — end-to-end workflows:
```python
def test_full_blitz_workflow():
    harness = BlitzHarness()
    harness.generate_synthetic_dataset(n_per_type=5)
    result = harness.run_blitz(n_configs=20)
    assert result.best_config is not None
    assert result.best_score > 0
```

### Step 3: Build Test Fixtures

Always use the built-in helpers for creating test data:

```python
from app.services.scoring.calibration.dataset import make_clean_segment, GroundTruth

def _make_labeled_segments(n_mistakes=5, n_clean=10):
    segments = []
    for i in range(n_mistakes):
        seg = make_clean_segment(f"mistake_{i}")
        seg.features["spoken_text"] = "The quick brown fax"  # Mismatch
        seg.features["issue_type"] = "substitution"
        seg.ground_truth = GroundTruth(is_mistake=True, priority="high")
        segments.append(seg.to_dict())
    for i in range(n_clean):
        segments.append(make_clean_segment(f"clean_{i}").to_dict())
    return segments
```

For baseline construction:
```python
from app.services.scoring.baseline import build_chapter_baseline

def _get_baseline(n_segments):
    dummy = [{"prosody_features_json": "{}", "audio_features_json": "{}"}] * n_segments
    return build_chapter_baseline(dummy, [], [])
```

### Step 4: Write Tests

**Naming convention**: `test_blitz_{module}.py`

**Test naming**: `test_{function_or_behavior}_{scenario}`

**Key principles**:
- Each test should be independent (no shared mutable state)
- Use `tmp_path` fixture for file I/O tests
- Keep test data small (5-20 segments, 10-20 configs) for speed
- Always test reproducibility with fixed seeds
- Test boundary conditions: empty inputs, single items, all-same labels

### Step 5: Run Tests

```bash
cd apps/api
PYTHONPATH=. pytest tests/test_blitz_*.py -v
```

## What To Test For Each Module

### config.py
- Default values are populated for all 15 detectors
- Hash is deterministic (same config = same hash)
- Hash changes when any parameter changes
- `to_dict()` / `from_dict()` roundtrip preserves all fields
- `save()` / `load()` file persistence
- `diff()` detects weight, threshold, and toggle changes
- `clone()` preserves values and sets parent_version
- `composite_weights` format matches `compute_all_composites()` expectations
- `detector_configs` format matches `run_all_detectors()` expectations
- `to_production_format()` outputs valid CalibrationProfile JSON

### dataset.py
- `make_clean_segment()` produces valid features with no defects
- `CalibrationDataset.split()` produces non-overlapping sets summing to total
- Stratified split maintains label proportions in each set
- Split is deterministic with same seed
- `merge()` deduplicates by segment_id
- `filter_by_narrator()` returns only matching segments
- Summary counts are correct

### perturbations.py
- Each of 8 perturbation types mutates expected features
- Combined perturbation applies 2-3 types
- Same seed = same result (reproducibility)
- Different seeds = different results
- Input features are never mutated (deep copy)
- Custom params override defaults
- `ground_truth_for_perturbation()` returns correct labels per type
- `generate_synthetic_dataset()` produces expected count
- Session drift is progressive (later = more degraded)
- Noise degradation scales with noise_level

### metrics.py
- Perfect predictions → F1 = 1.0
- All wrong → F1 = 0.0
- Empty inputs → all metrics = 0.0
- Ranking: identical rankings → Kendall tau = 1.0
- Ranking: reversed rankings → Kendall tau = -1.0
- Workload metrics: flag_rate = flagged/total
- Threshold sweep produces monotonic recall (decreasing with higher threshold)
- Combined score is bounded [0, 1]

### simulation.py
- Monte Carlo generates exact requested count
- All generated configs have unique hashes
- Grid search produces correct combinatorial count
- Latin Hypercube generates correct count with good coverage
- `run_simulation()` returns predictions for every segment
- `run_sweep()` tracks convergence and finds best

### optimizer.py
- Ranked results are sorted descending by score
- Pareto frontier contains only non-dominated points
- A point dominating another is correctly identified
- Early stopping triggers when score plateaus
- Ablation analysis sorts by absolute impact

### harness.py
- `run_blitz()` raises ValueError without dataset
- Grid search requires param_grid
- All three strategies (monte_carlo, grid, latin_hypercube) work
- `export()` creates expected files on disk
- Reproducibility: same seed = same best_config hash
- Ablation, threshold sweep, noise, drift tests complete without error

## Anti-Patterns To Avoid

- Don't test internal implementation details — test behavior
- Don't use large datasets in unit tests (keep under 30 segments)
- Don't rely on exact floating-point equality — use `abs(a - b) < epsilon` or `round()`
- Don't skip the reproducibility test — it catches hidden randomness
- Don't duplicate production code in tests — use the real scoring pipeline
- Don't hardcode expected metric values that depend on random configs — test structure and invariants instead
