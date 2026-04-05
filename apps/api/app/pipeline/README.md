# pipeline

Chapter analysis orchestrator. Runs every analysis stage in the correct order and writes progress back to the database so the UI can poll it.

## Contents

| File | Description |
|------|-------------|
| `analyze_chapter.py` | `run_analysis(...)` — the main entry point for a full chapter analysis run, invoked from `app.jobs.run_analysis_job` |

## Stage sequence

| Progress | Step | What happens |
|----------|------|-------------|
| 10 % | `prepare_inputs` | Copy source WAV to working directory; normalize and tokenize manuscript; write `manuscript_tokens.json` |
| 35 % | `transcribe` | Run WhisperX on the working audio; write `transcript.raw.json` |
| 60 % | `align` | Diff transcript against manuscript tokens; write `alignment.json` (contains token lists, `matches` opcodes, and `match_ratio`) |
| 60 % | `audio_analysis` | Extract RMS, ZCR, spectral centroid, click/cutoff markers via librosa; write `audio_signals.json` |
| 63 % | `vad` | Run Silero VAD to detect speech boundaries; write `vad_segments.json` |
| 66 % | `prosody` | Extract per-token F0 (pitch), speech rate, and energy contour; write `prosody_features.json` |
| 70 % | `detect_issues` | Run heuristic detectors; produce raw issue list |
| 74 % | `signal_fusion` | Enrich issues with audio-signal evidence |
| 77 % | `alt_take_clustering` | Group overlapping alternate takes by time overlap; write `alt_take_clusters.json` |
| 80 % | `scoring` | Run 15 primitive detectors → 5 composites → editorial recommendations; write `scoring_result.json` |
| 85 % | `triage_issues` | Optional LLM false-positive filtering; issues are then written to `issues.json` and persisted to SQLite |

## Error handling

Any unhandled exception in a stage sets the job status to `"failed"` and records the error message. Retrying a failed job reruns the pipeline from the start, although individual stages may reuse cached artifacts (e.g. `transcript.raw.json` is skipped on re-run if it already exists and `force_retranscribe` is not set).
