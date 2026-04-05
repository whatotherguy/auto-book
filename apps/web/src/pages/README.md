# pages

Page-level React components, one per application route. Each page owns its own data-fetching lifecycle and composes the reusable components from `../components/`.

## Pages

| File | Route | Description |
|------|-------|-------------|
| `ProjectsPage.tsx` | `/` | Lists all projects; provides create/delete project actions |
| `ProjectPage.tsx` | `/projects/:projectId` | Shows chapters in a project; handles chapter creation, WAV + manuscript upload, and triggering analysis |
| `ChapterReviewPage.tsx` | `/projects/:projectId/chapters/:chapterId` | Full chapter review UI — waveform, issue list, timeline, manuscript panel, alt-takes, ACX panel, and export controls |

## Responsibilities

- **Data fetching**: Pages call `api.ts` functions and manage loading/error state.
- **Layout**: Pages lay out the major panels (waveform, issues, manuscript) and pass data down to components.
- **Routing**: Pages read URL parameters via the router and use `routing.ts` helpers to build links.
- **Mutations**: Pages handle user actions (dismiss issue, export, start analysis) and refresh data after mutations.

## Adding a new page

1. Create `MyPage.tsx` in this directory.
2. Add a route constant to `../routing.ts`.
3. Register the route in `../App.tsx`.
