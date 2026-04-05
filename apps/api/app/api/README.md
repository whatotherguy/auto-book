# api

FastAPI route handlers. Each module registers a router that is mounted in `app/main.py`.

## Routers

| File | Prefix | Description |
|------|--------|-------------|
| `projects.py` | `/projects` | CRUD for `Project` records |
| `chapters.py` | `/projects/{id}/chapters` | Chapter creation, WAV / manuscript upload, chapter replacement |
| `jobs.py` | `/jobs` | Start analysis, poll job status, cancel jobs |
| `issues.py` | `/issues` | List, update, and dismiss detected issues |
| `exports.py` | `/exports` | Download CSV, JSON, and auto-edit WAV exports |
| `acx.py` | `/acx` | ACX-compliance check endpoints (RMS loudness, noise floor) |
| `calibration.py` | `/calibration` | Scoring-weight calibration admin (run sweep, promote profile) |
| `settings.py` | `/settings` | Read / update user-editable app settings |

## Conventions

- All handlers use dependency-injected `Session` objects from `app.db`.
- HTTP error responses use `fastapi.HTTPException` with standard status codes.
- Heavy work (transcription, alignment, scoring) is offloaded to background tasks via `app.jobs`; endpoints return immediately with a job ID.
- Request and response bodies are typed with schemas from `app.schemas`.
