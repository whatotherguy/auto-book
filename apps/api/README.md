# API

FastAPI backend for Audiobook Editor.

## Responsibilities
- project/chapter CRUD
- uploads
- analysis jobs
- issue storage
- exports

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
