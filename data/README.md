# data

Local runtime storage directory. This is where the application writes all persistent state that is not kept in the SQLite database.

> **This directory is local-only and is not committed to version control** (except for `.gitkeep` and the database file used in development).

## Structure at runtime

```
data/
├── audiobook_editor.db          ← SQLite database (projects, chapters, issues, jobs, …)
└── projects/
    └── <project_id>/
        └── chapters/
            └── <chapter_number>/
                ├── source/      ← original uploaded WAV (never modified)
                ├── working/     ← normalised working copy used for analysis
                ├── analysis/    ← intermediate artifacts (JSON)
                │   ├── manuscript_tokens.json
                │   ├── transcript.raw.json
                │   ├── spoken_tokens.json
                │   ├── alignment.json
                │   ├── audio_signals.json
                │   ├── vad_segments.json
                │   ├── prosody_features.json
                │   ├── alt_take_clusters.json
                │   ├── scoring_result.json
                │   ├── issues.json
                │   └── acx_report.json      ← written by the ACX endpoint
                └── exports/     ← generated CSV, JSON, and WAV exports
```

## Artifact retention

All intermediate artifacts are intentionally kept on disk after analysis completes so that failures can be debugged and individual pipeline stages can be re-run without starting over.

## Database files

| File | Description |
|------|-------------|
| `audiobook_editor.db` | Main SQLite database |
| `audiobook_editor.db-shm` | SQLite shared-memory file (created at runtime) |
| `audiobook_editor.db-wal` | SQLite write-ahead log (created at runtime) |

Run `alembic upgrade head` from `apps/api/` to initialise or migrate the database schema.
