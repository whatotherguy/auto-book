# src

Frontend source for the Audiobook Editor browser UI.

## File map

| File | Description |
|------|-------------|
| `main.tsx` | React entry point — mounts `<App />` into `index.html` |
| `App.tsx` | Root component — sets up client-side routing between the three pages |
| `api.ts` | All `fetch` calls to the backend REST API, typed with response interfaces |
| `types.ts` | Shared TypeScript types (`Project`, `Chapter`, `Issue`, `Job`, `ScoringResult`, …) |
| `routing.ts` | Route path constants and helper to build typed URLs |
| `cache.ts` | Simple in-memory response cache to reduce redundant API calls |
| `utils.ts` | Small UI helpers (format duration, issue type labels, confidence badge colour, …) |
| `styles.css` | Global CSS (Tailwind base + custom component styles) |
| `vite-env.d.ts` | Vite client-type declarations |
| [`components/`](components/) | Reusable React components |
| [`pages/`](pages/) | Page-level components (one per route) |

## Data flow

```
pages/*          ← route components, own the data-fetch lifecycle
  └─ api.ts      ← typed fetch wrappers
  └─ components/ ← pure/controlled presentational components
       └─ types.ts / utils.ts  ← shared types and helpers
```

Pages are responsible for fetching data and passing it down as props. Components do not call `api.ts` directly (with the exception of mutation-only components such as `IssueList`).
