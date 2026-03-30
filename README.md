# Audiobook Editor

Local-first review tool for audiobook narration editing.

## Purpose
This app helps review raw audiobook chapter narration by:
- transcribing the audio,
- comparing it to the chapter manuscript,
- flagging likely edit-worthy spots,
- showing them in a browser waveform review UI,
- exporting review/cut lists for manual editing.

## v1 scope
Review-first only. No destructive editing of source WAV files.

## Stack
- Backend: FastAPI + Python + SQLite
- Frontend: React + TypeScript + Vite
- Audio/transcription: FFmpeg + WhisperX
- Waveform UI: wavesurfer.js

## Monorepo structure
- `apps/api` - backend API and analysis pipeline
- `apps/web` - browser UI
- `docs` - architecture, heuristics, test plan
- `data` - local working files and artifacts

## Local development

Start the backend and frontend in separate terminals.

### Backend
```bash
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd apps/web
npm install
npm run dev
```
### Run Tests
npm run tests

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

For dramatically faster transcription (45 min -> 3 min per hour of audio):

```bash
cd apps/api
python setup_gpu.py
```

This installs PyTorch with CUDA support and downloads the large-v3 Whisper model.
Requires an NVIDIA GPU with 4+ GB VRAM. The app auto-detects GPU on startup.

### Transcription tuning
- `WHISPERX_PROFILE=balanced` is the practical default for long CPU transcription jobs.
- Set `WHISPERX_PROFILE=high_quality` for slower, better decoding on difficult audio.
- Set `WHISPERX_PROFILE=max_quality` or `WHISPERX_MODEL=large-v3` only when you explicitly want the slowest, highest-cost run.
- Leave `WHISPERX_MODEL` blank to let the profile choose a sane model automatically.

## Notes
- Original uploaded WAV files must remain untouched.
- Analysis artifacts are stored on disk for debugging and iteration.
