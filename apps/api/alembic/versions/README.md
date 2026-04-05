# alembic/versions

Alembic database migration scripts. Each file is an incremental revision that evolves the SQLite schema.

## Migrations (in order)

| Revision | File | Description |
|----------|------|-------------|
| `f0a1c2b3d4e5` | `f0a1c2b3d4e5_initial_schema.py` | Initial schema — `project`, `chapter`, `issue`, `analysisJob` tables |
| `a1b2c3d4e5f6` | `a1b2c3d4e5f6_add_signal_scoring_tables.py` | Add `audiosignal`, `vadsegment`, `alttakecluster`, `alttakemember`, `scoringresult`, `calibrationprofile` tables; extend `issue` with signal/scoring columns |
| `b2c3d4e5f6a7` | `b2c3d4e5f6a7_add_triage_columns.py` | Add `triage_label`, `triage_confidence`, `triage_note` columns to `issue` |

## Running migrations

```bash
cd apps/api
alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back one revision
alembic current               # show current revision
```

## Creating a new migration

After changing `app/models.py`, auto-generate a migration:

```bash
alembic revision --autogenerate -m "short description"
```

Review the generated file in this directory before applying it — `--autogenerate` can miss some changes (e.g. column type changes in SQLite).
