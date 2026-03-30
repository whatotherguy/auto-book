# AGENTS.md

## Project
Audiobook Editor

## Goal
Build a local-first web application that helps review raw audiobook narration by:
1. ingesting a chapter WAV and chapter manuscript text,
2. transcribing the narration,
3. aligning spoken words to the manuscript,
4. detecting likely edit-worthy issues,
5. presenting them in a browser review UI with waveform + manuscript context,
6. exporting a cut/review list for manual editing in Adobe Audition.

This version is review-first. It must NOT destructively edit the original source audio.

---

## Product constraints

### In scope
- Local-only processing
- Chapter-by-chapter workflow
- WAV input
- TXT or pasted manuscript text input
- Transcription and rough alignment
- Detection of:
  - false starts
  - repeated words/phrases
  - pickup restarts
  - missing text
  - suspicious long pauses
- Browser UI with waveform and issue review
- CSV and JSON export

### Out of scope
- Cloud sync
- Accounts/auth
- Team collaboration
- Multitrack editing
- Direct Adobe Audition plugin integration
- Auto-editing master audio
- Noise reduction/mastering
- Marketplace/commercial packaging

---

## Required architecture

### Backend
- Python 3.11+
- FastAPI
- SQLite
- SQLAlchemy or SQLModel
- FFmpeg
- WhisperX

### Frontend
- React
- TypeScript
- Vite
- wavesurfer.js
- Simple CSS or Tailwind

### Storage model
- SQLite for app state
- Local filesystem for source files and generated artifacts

---

## Non-negotiable implementation rules

1. Never modify the original uploaded WAV.
2. Always create a working copy for analysis.
3. Persist intermediate artifacts so failures can be debugged:
   - normalized manuscript tokens
   - transcript output
   - spoken tokens with timestamps
   - alignment output
   - issue output
4. Favor simple, inspectable code over clever abstractions.
5. Keep functions small and testable.
6. Prefer deterministic heuristics over LLM calls.
7. The first version should work fully offline after dependencies are installed.
8. The UI should be useful even if alignment is imperfect.
9. Every issue needs:
   - type
   - start_ms
   - end_ms
   - confidence
   - expected_text
   - spoken_text
   - context_before
   - context_after
10. Never silently drop low-confidence data; surface it as uncertain/manual review.

---

## Priority order

1. Backend ingestion
2. Text normalization and tokenization
3. WhisperX transcription wrapper
4. Spoken token persistence
5. Alignment/diff pipeline
6. Issue detection heuristics
7. Export endpoints
8. Review UI
9. Waveform interaction polish
10. Test coverage

---

## Issue taxonomy

Use only these issue types for v1:
- false_start
- repetition
- pickup_restart
- substitution
- missing_text
- long_pause
- uncertain_alignment

Do not invent extra categories unless absolutely necessary.

---

## Confidence rules

Suggested bands:
- 0.85 to 1.00 = high
- 0.65 to 0.84 = medium
- below 0.65 = low / manual review

Confidence should be heuristic and explainable.

---

## File handling rules

For each chapter, store artifacts under:

data/projects/<project_id>/chapters/<chapter_number>/
  source/
  working/
  analysis/
  exports/

Expected analysis artifacts:
- transcript.raw.json
- manuscript_tokens.json
- spoken_tokens.json
- alignment.json
- issues.json

Expected exports:
- issues.csv
- issues.json

---

## Backend conventions

- Keep routes thin
- Put logic into services/pipeline modules
- Use Pydantic models for request/response schemas
- Add health endpoint
- Use explicit response models
- Return stable JSON shapes

---

## Frontend conventions

- Keep pages thin
- Put waveform behavior inside WaveformPanel
- Centralize API calls in one file
- Strongly type server responses
- Make issue review keyboard-friendly later, but not required in first commit

---

## Testing requirements

Must include unit tests for:
- normalization
- tokenization
- repetition detection
- false start detection
- timecode formatting

If implementation is incomplete, still scaffold the tests with TODO markers.

---

## Definition of done for v1

A user can:
1. create a project,
2. create a chapter,
3. upload a WAV,
4. paste or upload the chapter text,
5. run analysis,
6. open a browser review page,
7. click through detected issues,
8. inspect waveform + manuscript context,
9. approve/reject issues,
10. export CSV/JSON review lists.

---

## Build style

When implementing:
- finish vertical slices
- do not leave half-connected modules
- prefer a small working pipeline over a large speculative architecture
- keep comments concise and useful
- add TODO comments only where they clearly indicate next implementation steps

---

## First milestone to complete

Complete the following before moving on:
- FastAPI app boots
- React app boots
- project/chapter CRUD works locally
- WAV upload works
- text submission works
- chapter data persists
- review page renders placeholder waveform and issue list

Then continue with the analysis pipeline.
