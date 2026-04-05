# tests

Pytest test suite for the backend. All tests run against an in-memory SQLite database and do not require a running server or real audio files.

## Running tests

```bash
cd apps/api
pytest                        # run all tests
pytest tests/test_normalize.py  # run a single file
pytest -k "blitz"             # run tests matching a keyword
```

Or from the repo root:

```bash
npm test
```

## Test files

### Core pipeline
| File | What it covers |
|------|----------------|
| `test_db.py` | Database initialisation and model creation |
| `test_normalize.py` | Text normalisation (`text_normalize.py`) |
| `test_tokenization.py` | Tokenisation helpers (`utils/tokenization.py`) |
| `test_timecode.py` | Timecode formatting (`utils/timecode.py`) |
| `test_transcribe.py` | WhisperX wrapper (mocked) |
| `test_manuscript_extract.py` | Manuscript parsing |
| `test_alignment_issues.py` | Alignment edge cases |
| `test_alignment_match_ratio.py` | Alignment quality metric |

### Issue detection
| File | What it covers |
|------|----------------|
| `test_detect_false_start.py` | False-start heuristic |
| `test_detect_long_pause.py` | Long-pause heuristic |
| `test_detect_repetition.py` | Repetition heuristic |
| `test_detection_config.py` | Detection configuration schema |
| `test_new_detection_config.py` | Updated detection config fields |
| `test_cascade_delete.py` | Issue cascade-delete on chapter delete |

### Scoring engine
| File | What it covers |
|------|----------------|
| `test_scoring_detectors.py` | All 15 primitive detectors |
| `test_scoring_pipeline.py` | `run_scoring_pipeline()` end-to-end |
| `test_composite.py` | Composite score formulas |
| `test_derived_features.py` | Derived feature computation |
| `test_signal_fusion.py` | Signal enrichment merging |
| `test_take_ranking.py` | Alternate-take ranking |
| `test_recommendations.py` | Editorial recommendation generation |
| `test_audio_analysis.py` | Audio signal feature extraction (mocked librosa) |
| `test_issues_endpoints.py` | Issues REST endpoints |

### Calibration (Blitz)
| File | What it covers |
|------|----------------|
| `test_blitz_harness.py` | `BlitzHarness` end-to-end workflow |
| `test_blitz_config.py` | `ScoringConfig` / `ConfigStore` |
| `test_blitz_dataset.py` | `CalibrationDataset` loading and validation |
| `test_blitz_metrics.py` | Evaluation metrics (`evaluate_full`, `threshold_sweep`) |
| `test_blitz_optimizer.py` | Monte Carlo optimizer |
| `test_blitz_perturbations.py` | Synthetic dataset perturbations |
| `test_blitz_simulation.py` | `simulate_scoring()` without database |
| `test_blitz_advanced.py` | Narrator profiles and ablation studies |
| `test_calibration.py` | Calibration REST endpoints |

### Alt-takes & exports
| File | What it covers |
|------|----------------|
| `test_alt_takes.py` | Alt-take clustering logic |
| `test_alt_take_clusters_endpoint.py` | Alt-take REST endpoint |
| `test_auto_edit_export.py` | Auto-edit WAV export |
| `test_replace_chapter_audio.py` | Chapter audio replacement endpoint |
| `test_acx.py` | ACX compliance measurement |

## Fixtures and conventions

- Tests use `pytest` fixtures defined inline or in small helper functions.
- Database sessions use `app.db.get_session` with an in-memory SQLite URL.
- External dependencies (WhisperX, librosa, torch) are mocked with `unittest.mock.patch`.
- No test writes to the real `data/` directory.
