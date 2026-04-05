# services

Individual service modules that implement each analysis step. Each module is a collection of pure (or near-pure) functions; no global state is held.

## Module reference

### Audio I/O & preprocessing
| File | Description |
|------|-------------|
| `audio.py` | WAV reading helpers (`read_wav_duration_ms`, header validation) |
| `ingest.py` | Prepare working audio copy; write JSON artifact files to disk |
| `storage.py` | Ensure per-chapter directory tree (`source/`, `working/`, `analysis/`, `exports/`) |

### Transcription & alignment
| File | Description |
|------|-------------|
| `transcribe.py` | WhisperX wrapper — GPU/CPU detection, model selection, returns word-level timestamps |
| `transcribe_api.py` | Thin HTTP wrapper for calling an external transcription service (optional) |
| `text_normalize.py` | Manuscript text cleaning: strip punctuation, expand contractions, lowercase |
| `manuscript.py` | Parse manuscript file, split into chapters, extract clean tokens |
| `align.py` | Diff-based alignment of transcript tokens against manuscript tokens; `build_alignment(...)` returns a dict with token lists, `matches` opcodes, and `match_ratio` |

### Audio signal analysis
| File | Description |
|------|-------------|
| `audio_analysis.py` | librosa-based feature extraction: RMS dB, ZCR, spectral centroid, click/cutoff detection |
| `vad.py` | Silero VAD integration — detects speech/silence boundaries at millisecond resolution |
| `prosody.py` | Per-token F0 (pyin), speech rate, and energy contour extraction |
| `signal_fusion.py` | Merge audio-signal evidence into issue records (enrich `has_click`, `rms_db`, etc.) |

### Issue detection
| File | Description |
|------|-------------|
| `detect.py` | Heuristic detectors for the 7 issue types (`false_start`, `repetition`, `pickup_restart`, `substitution`, `missing_text`, `long_pause`, `uncertain_alignment`) |
| `alt_takes.py` | Cluster overlapping time ranges into alternate-take groups; rank takes by quality |

### Scoring & recommendations
| File | Description |
|------|-------------|
| [`scoring/`](scoring/) | Full heuristic scoring engine (see sub-package README) |

### Export & QA
| File | Description |
|------|-------------|
| `export.py` | Build CSV and JSON export payloads; generate auto-edit WAV splice list |
| `triage.py` | Optional LLM-based false-positive filtering on detected issues |
| `acx.py` | ACX loudness/noise-floor compliance measurement |
| `gpu_thermal.py` | GPU temperature monitoring to throttle transcription on hot hardware |

## Conventions

- Functions take plain Python primitives or SQLModel instances as arguments.
- Functions do **not** hold open database sessions; sessions are passed in by the pipeline.
- Disk I/O uses `pathlib.Path` throughout.
