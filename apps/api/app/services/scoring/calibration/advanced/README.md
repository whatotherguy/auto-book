# advanced

Advanced calibration extensions for narrator-specific tuning and systematic ablation studies.

## Files

| File | Description |
|------|-------------|
| `narrator.py` | `NarratorProfile` — per-narrator weight overrides; build and merge narrator-specific configs from a labelled dataset split by `narrator_id` |
| `ablation.py` | `run_ablation_study()` — systematically disable one detector at a time and measure performance impact; helps identify which detectors contribute most to accuracy |

## When to use these

- **`narrator.py`**: When a specific narrator has quirks (unusually fast pace, naturally low energy) that cause the default weights to generate too many false positives. Build a profile with their labelled sessions and pass it to `BlitzHarness` as a `narrator_id` override.
- **`ablation.py`**: When evaluating whether a new detector is actually adding value, or when trying to simplify the engine by removing low-value detectors.

## Integration

Both modules are called from `BlitzHarness` in the parent package. They are not intended to be used standalone, but their public functions are unit-tested in `tests/test_blitz_advanced.py`.
