# app

Core Python package for the Audiobook Editor backend.

## Module map

| Module / Package | Purpose |
|-----------------|---------|
| `main.py` | FastAPI app definition / configuration, CORS config, startup health checks |
| `config.py` | Environment-driven settings (Pydantic `Settings`) |
| `db.py` | SQLite engine, session factory, `init_db()` |
| `models.py` | SQLModel ORM models (`Project`, `Chapter`, `Issue`, `AnalysisJob`, `ScoringResult`, etc.) |
| `schemas.py` | Pydantic request/response schemas used by the API layer |
| `jobs.py` | Background job runner — launches analysis pipeline tasks |
| `detection_config.py` | Default thresholds and weights for issue detection heuristics |
| [`api/`](api/) | FastAPI route handlers (projects, chapters, issues, exports, …) |
| [`pipeline/`](pipeline/) | End-to-end chapter analysis orchestrator |
| [`services/`](services/) | Discrete service modules (transcription, alignment, detection, scoring, …) |
| [`utils/`](utils/) | Small shared helpers (timecode formatting, tokenization) |

## Dependency flow

```
api/          ← HTTP boundary
  └─ jobs.py  ← launches background tasks
       └─ pipeline/analyze_chapter.py  ← orchestrates all analysis steps
            └─ services/*              ← individual analysis modules
                 └─ models.py / db.py  ← persistence
```

## Key design rules

- **Original WAV is never modified.** A working copy is created in `data/projects/<id>/chapters/<n>/working/`.
- All intermediate artifacts are written to disk for debugging (`analysis/` sub-directory per chapter).
- Services are stateless functions; all state lives in the SQLite database or on disk.
