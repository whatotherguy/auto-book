# Audiobook Editor

Local-first review tool for audiobook narration editing.

## Purpose
This app helps review raw audiobook chapter narration by:
- transcribing the audio,
- comparing it to the chapter manuscript,
- flagging likely edit-worthy spots (11 issue types),
- analyzing audio signals (clicks, cutoffs, silences, onsets),
- detecting alternate takes and ranking them by quality,
- scoring issues with 15 primitive detectors and 5 composite scores,
- generating editorial recommendations (auto-cut, review, pickup, etc.),
- showing them in a browser waveform review UI with signal overlays,
- exporting review/cut lists with scoring data for manual editing.

## v2 scope (current)
Signal-enhanced detection, heuristic scoring engine, alt-take clustering, calibration harness, and auto-edit readiness.

## Stack
- Backend: FastAPI + Python + SQLite
- Frontend: React + TypeScript + Vite
- Audio/transcription: FFmpeg + WhisperX
- Audio analysis: librosa (RMS, ZCR, spectral, prosody/pyin)
- VAD: Silero VAD (via torch.hub)
- Waveform UI: wavesurfer.js

## Monorepo structure
- `apps/api` - backend API and analysis pipeline
  - `app/services/` - core services (transcribe, align, detect, triage, export)
  - `app/services/audio_analysis.py` - audio signal extraction (clicks, cutoffs, silences)
  - `app/services/vad.py` - Silero VAD speech boundary detection
  - `app/services/prosody.py` - per-token F0/pitch, speech rate, energy contour
  - `app/services/signal_fusion.py` - merge signals into enriched issues
  - `app/services/alt_takes.py` - alternate take clustering
  - `app/services/scoring/` - heuristic scoring engine
    - `detectors/` - 15 primitive detectors (text, timing, audio, prosody, context)
    - `composite.py` - 5 composite score formulas
    - `recommendations.py` - editorial recommendation engine
    - `calibration/` - offline Monte Carlo weight tuning
  - `app/api/calibration.py` - calibration admin endpoints
- `apps/web` - browser UI
  - `components/AltTakesPanel.tsx` - alt-take review and selection
- `docs` - architecture, heuristics, test plan
- `data` - local working files and artifacts

## Local development

Start the backend and frontend in separate terminals.

### Backend

```bash
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --port 8000
```

If you have an NVIDIA GPU, install PyTorch with CUDA before the `pip install -e` step (see GPU Transcription below).

### Frontend
```bash
cd apps/web
npm install
npm run dev
```

After the first install, use `npm run web` from the repo root instead.
### Run Tests
```bash
npm test
```

### Quick start
If the virtualenv and dependencies are already installed:

```bash
npm run api   # terminal 1 — backend on :8000
npm run web   # terminal 2 — frontend on :5173
```

Or start both at once with prefixed output:

```bash
npm run dev
```

## Environment
Copy `.env.example` to `.env` in `apps/api` if needed.

### GPU Transcription (Recommended)

For dramatically faster transcription (45 min -> 3 min per hour of audio). Requires an NVIDIA GPU with 4+ GB VRAM.

After creating and activating the venv, install PyTorch with CUDA **before** installing the project dependencies:

```bash
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

Then continue with `python -m pip install -e ".[dev]"` as normal. The app auto-detects GPU on startup.

### Transcription tuning
- `WHISPERX_PROFILE=balanced` is the practical default for long CPU transcription jobs.
- Set `WHISPERX_PROFILE=high_quality` for slower, better decoding on difficult audio.
- Set `WHISPERX_PROFILE=max_quality` or `WHISPERX_MODEL=large-v3` only when you explicitly want the slowest, highest-cost run.
- Leave `WHISPERX_MODEL` blank to let the profile choose a sane model automatically.

## Database migrations

After upgrading, run the Alembic migration to add signal/scoring tables:

```bash
cd apps/api
alembic upgrade head
```

This adds: `audiosignal`, `vadsegment`, `alttakecluster`, `alttakemember`, `scoringresult`, `calibrationprofile` tables and extends `issue` with signal/scoring columns.

## Analysis pipeline

The analysis pipeline processes chapters in these stages:

| Progress | Step | Description |
|----------|------|-------------|
| 10% | prepare_inputs | Copy audio, normalize text |
| 35% | transcribe | WhisperX GPU transcription |
| 55% | align | Token-level manuscript alignment |
| 60% | audio_analysis | RMS, ZCR, spectral, click/cutoff detection |
| 63% | vad | Silero VAD speech boundaries |
| 66% | prosody | Per-token F0, speech rate, energy |
| 70% | detect_issues | Issue detection (11 types) |
| 74% | signal_fusion | Enrich issues with signal data |
| 77% | alt_take_clustering | Group overlapping takes |
| 80% | scoring | 15 detectors, 5 composites, recommendations |
| 85% | triage_issues | Optional LLM false-positive filtering |
| 90% | persist | Save to database |

## Calibration

The scoring weights can be tuned offline using the calibration system:

1. Create labeled datasets in `apps/api/app/data/calibration/<name>/labels.json`
2. Run a Monte Carlo sweep via `POST /calibration/sweep`
3. The best weights are saved as a `CalibrationProfile` and used for future analyses

## Notes
- Original uploaded WAV files must remain untouched.
- Analysis artifacts are stored on disk for debugging and iteration.
- `librosa` is required for audio feature extraction. Install with `pip install -e ".[dev]"`.
- Silero VAD requires `torch` and `torchaudio` (included with GPU install).
