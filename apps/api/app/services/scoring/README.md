# scoring

Heuristic scoring engine. Takes raw issue records (from the detection pipeline) and enriches each one with a multi-dimensional score, composite signals, and an editorial recommendation.

## Architecture

```
pipeline.py          ← main entry point: run_scoring_pipeline()
   ├── features.py          extract raw feature dict per issue
   ├── derived_features.py  compute secondary features from raws
   ├── baseline.py          build chapter-level baseline statistics
   ├── envelope.py          time-domain score envelope (temporal context)
   ├── detector_registry.py run all primitive detectors and collect outputs
   │    └── detectors/      15 primitive detector functions (see sub-package)
   ├── composite.py         5 composite score formulas
   ├── take_ranking.py      rank alternate takes by composite score
   ├── recommendations.py   map composite scores → editorial action
   └── detector_output.py   DetectorOutput dataclass
```

## Files

| File | Description |
|------|-------------|
| `pipeline.py` | `run_scoring_pipeline()` — top-level entry point; loads calibration profile, calls all sub-steps |
| `features.py` | `extract_raw_features()` — pull signal values out of an issue record dict |
| `derived_features.py` | Compute ratios, flags, and bucketed values from raw features (e.g. RMS drop ratio, pause-to-speech ratio) |
| `baseline.py` | Build per-chapter baseline statistics (median RMS, typical pause length, etc.) used to normalise detector inputs |
| `envelope.py` | Build a time-ordered score envelope so nearby high-scoring issues can influence each other |
| `detector_registry.py` | `run_all_detectors()` — iterates over all 15 registered detectors and collects `DetectorOutput` objects |
| `detector_output.py` | `DetectorOutput` dataclass: `detector_name`, `score`, `confidence`, `reasons`, `features_used`, `triggered` |
| `composite.py` | `compute_all_composites()` — 5 composite scores: `mistake_candidate`, `pickup_candidate`, `performance_quality`, `continuity_fit`, `splice_readiness` |
| `take_ranking.py` | `rank_alternate_takes()` — sort alt-take clusters using the composite scores from `compute_all_composites()` |
| `recommendations.py` | `generate_recommendation()` — maps composite scores to one of: `safe_auto_cut`, `review_mistake`, `likely_pickup`, `alt_take_available`, `no_action` |
| [`detectors/`](detectors/) | 15 primitive detector functions grouped by signal domain |
| [`calibration/`](calibration/) | Offline Monte Carlo weight tuning harness |

## Calibration

Detector weights can be tuned offline. The active `CalibrationProfile` is loaded from SQLite at pipeline start and applied as weight overrides. If no profile is active, all detectors use equal weights.
