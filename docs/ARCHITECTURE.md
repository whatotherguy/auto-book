# Architecture

## Overview
Two-app local monorepo:

- `apps/api`: FastAPI backend, SQLite DB, analysis pipeline
- `apps/web`: React review UI

## Data flow
1. User creates project
2. User creates chapter
3. User uploads WAV and manuscript text
4. Backend stores source files
5. User starts analysis
6. Backend runs analysis pipeline
7. Pipeline writes artifacts and DB records
8. UI polls job status
9. User reviews issues in waveform UI
10. User exports CSV/JSON

## Chapter storage
data/projects/<project_id>/chapters/<chapter_number>/
- source/
- working/
- analysis/
- exports/

## Design principle
Prefer editorially useful alignment over perfect phonetic alignment in v1.
