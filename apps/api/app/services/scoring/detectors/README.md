# detectors

The 15 primitive detector functions. Each detector receives a `features` dict and a `derived` dict and returns a `DetectorOutput` with a score in [0, 1] and a human-readable reason list.

> **Detectors vs. issue types**: The 15 detectors here are *scoring* components — they measure signal evidence and contribute weighted scores to composite results. They are distinct from the 7 *issue types* (`false_start`, `repetition`, `pickup_restart`, `substitution`, `missing_text`, `long_pause`, `uncertain_alignment`) that are produced by the detection pipeline in `services/detect.py`.

## Files

| File | Detectors inside | Signal domain |
|------|-----------------|---------------|
| `audio.py` | `detect_click_transient`, `detect_clipping`, `detect_room_tone_shift`, `detect_punch_in_boundary` | Raw audio signal anomalies |
| `timing.py` | `detect_long_pause`, `detect_rush`, `detect_timing_irregularity` | Token-level timing / pace |
| `text.py` | `detect_text_mismatch`, `detect_repetition`, `detect_missing_text` | Transcript ↔ manuscript alignment |
| `prosody.py` | `detect_pitch_anomaly`, `detect_energy_drop`, `detect_speech_rate_anomaly` | Pitch (F0), energy, and speech-rate signals |
| `context.py` | `detect_false_start`, `detect_pickup_restart` | Sequential-context patterns (surrounding tokens) |

## Detector contract

Every detector must:

1. Accept `(features: dict, derived: dict, config: dict | None)` as positional arguments.
2. Return a `DetectorOutput` instance (import from `..detector_output`).
3. Never raise exceptions for missing keys — use `.get()` with safe defaults.
4. Set `triggered = True` only when `score >= threshold` (default threshold lives in `config` or falls back to a module constant).

## Adding a new detector

1. Implement the function in the appropriate domain file (or create a new one).
2. Register it in `../detector_registry.py` by adding it to `ALL_DETECTORS`.
3. Add its name to `ALL_DETECTOR_NAMES` in `../calibration/config.py`.
4. Write a test in `tests/test_scoring_detectors.py`.
