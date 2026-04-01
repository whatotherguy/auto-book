# API

FastAPI backend for Audiobook Editor.

## Responsibilities
- project/chapter CRUD
- uploads
- analysis jobs (transcription, alignment, signal extraction, scoring)
- audio signal analysis (RMS, ZCR, spectral centroid, click/cutoff detection)
- VAD speech boundary detection (Silero VAD)
- prosody extraction (F0/pitch, speech rate, energy contour)
- signal fusion and enrichment
- alt-take clustering and ranking
- heuristic scoring engine (15 detectors, 5 composites, recommendations)
- calibration system (Monte Carlo weight tuning)
- issue storage
- exports (CSV with scoring data, JSON, edited WAV with auto-approve)

## Run
```bash
uvicorn app.main:app --reload --port 8000
```

## Database migrations

Run the current schema on the database:
```bash
alembic upgrade head
```

Create a new migration after changing models:
```bash
alembic revision --autogenerate -m "description"
```
