# api

FastAPI route handlers. Each module registers a router that is mounted in `app/main.py`.

## Routers

| File | Primary route patterns | Description |
|------|------------------------|-------------|
| `projects.py` | `/projects`, `/projects/{project_id}` | CRUD for `Project` records |
| `chapters.py` | `/projects/{project_id}/chapters`, `/chapters/{chapter_id}/*` | Chapter creation, WAV / manuscript upload, chapter replacement, alignment, alt-takes, scoring summary |
| `jobs.py` | `/jobs/{job_id}`, `/chapters/{chapter_id}/analysis-job` | Poll job status, cancel jobs |
| `issues.py` | `/chapters/{chapter_id}/issues`, `/issues/{issue_id}` | List, update, and dismiss detected issues |
| `exports.py` | `/chapters/{chapter_id}/exports/*` | Download CSV, JSON, and auto-edit WAV exports |
| `acx.py` | `/chapters/{chapter_id}/acx-check` | ACX-compliance check endpoints (RMS loudness, noise floor) |
| `calibration.py` | `/calibration/profiles`, `/calibration/datasets`, `/calibration/sweep` | Scoring-weight calibration admin (run sweep, manage profiles) |
| `settings.py` | `/settings`, `/settings/gpu-status` | Read / update user-editable app settings |

## Conventions

- All handlers use dependency-injected `Session` objects from `app.db`.
- HTTP error responses use `fastapi.HTTPException` with standard status codes.
- Heavy work (transcription, alignment, scoring) is offloaded to background tasks via `app.jobs`; endpoints return immediately with a job ID.
- Request and response bodies are typed with schemas from `app.schemas`.
