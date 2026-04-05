# pipeline

Chapter analysis orchestrator. Runs every analysis stage in the correct order and writes progress back to the database so the UI can poll it.

## Contents

| File | Description |
|------|-------------|
| `analyze_chapter.py` | `analyze_chapter()` — the single entry point for a full chapter analysis run |

## Stage sequence

| Progress | Step | What happens |
|----------|------|-------------|
| 10 % | `prepare_inputs` | Copy source WAV to working directory; normalize and tokenize manuscript |
| 35 % | `transcribe` | Run WhisperX on the working audio; write transcript JSON |
| 55 % | `align` | Diff transcript against manuscript tokens; produce aligned token list |
| 60 % | `audio_analysis` | Extract RMS, ZCR, spectral centroid, click/cutoff markers via librosa |
| 63 % | `vad` | Run Silero VAD to detect speech boundaries |
| 66 % | `prosody` | Extract per-token F0 (pitch), speech rate, and energy contour |
| 70 % | `detect_issues` | Run heuristic detectors; produce raw issue list |
| 74 % | `signal_fusion` | Enrich issues with audio-signal evidence |
| 77 % | `alt_take_clustering` | Group overlapping alternate takes by time overlap |
| 80 % | `scoring` | Run 15 primitive detectors → 5 composites → editorial recommendations |
| 85 % | `triage_issues` | Optional LLM false-positive filtering |
| 90 % | `persist` | Write issues, scoring results, and artifacts to SQLite |

## Error handling

Any unhandled exception in a stage sets the job status to `"failed"` and records the error message. Completed stages are **not** re-run on retry; the pipeline is designed to be re-entrant at the step level when needed.
