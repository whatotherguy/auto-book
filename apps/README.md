# apps

This directory contains the two applications that make up the Audiobook Editor monorepo.

## Contents

| Directory | Description |
|-----------|-------------|
| [`api/`](api/) | Python/FastAPI backend — analysis pipeline, database, and REST API |
| [`web/`](web/) | React/TypeScript frontend — browser-based waveform review UI |

## How they fit together

```
apps/
├── api/   ← backend server on :8000  (FastAPI + SQLite)
└── web/   ← frontend dev server on :5173 (Vite + React)
```

The frontend calls the backend over HTTP. In development both processes run locally; no cloud services are required.

## Starting both apps

From the repo root:

```bash
npm run dev        # starts api + web with prefixed output
```

Or individually:

```bash
npm run api        # backend only
npm run web        # frontend only
```

See the root [`README.md`](../README.md) for full setup instructions including virtual-environment creation, GPU transcription, and database migrations.
