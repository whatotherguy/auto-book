# API Contract

## Health
- GET /health

## Projects
- POST /projects
- GET /projects
- GET /projects/{project_id}

## Chapters
- POST /projects/{project_id}/chapters
- GET /chapters/{chapter_id}
- POST /chapters/{chapter_id}/audio
- POST /chapters/{chapter_id}/text

## Jobs
- POST /chapters/{chapter_id}/analyze
- GET /jobs/{job_id}

## Issues
- GET /chapters/{chapter_id}/issues
- PATCH /issues/{issue_id}

## Exports
- POST /chapters/{chapter_id}/exports/csv
- POST /chapters/{chapter_id}/exports/json
