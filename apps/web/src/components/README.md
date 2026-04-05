# components

Reusable React components used across the review UI. None of these components are tied to a specific route — they receive all data via props.

## Component reference

### Layout & navigation
| Component | Description |
|-----------|-------------|
| `Breadcrumb.tsx` | Breadcrumb trail showing Project → Chapter hierarchy with links |
| `CollapsibleSection.tsx` | Accordion wrapper with an animated expand/collapse toggle |
| `Skeleton.tsx` | Loading-state placeholder shimmer blocks |
| `Tooltip.tsx` | Hover tooltip with configurable placement |
| `ErrorBoundary.tsx` | React error boundary — catches render errors and shows a fallback message |

### Issue review
| Component | Description |
|-----------|-------------|
| `IssueList.tsx` | Scrollable list of detected issues; supports filter, sort, and dismiss actions |
| `IssueDetail.tsx` | Expanded single-issue view showing scoring breakdown, signal data, and editorial recommendation |
| `IssueTimeline.tsx` | Horizontal time-ruler showing issue markers at their `start_ms` positions |

### Waveform & playback
| Component | Description |
|-----------|-------------|
| `WaveformPanel.tsx` | wavesurfer.js waveform with region markers for each issue; controls playback and seek |
| `FollowAlongPanel.tsx` | Manuscript text panel that highlights the word currently being played |
| `ManuscriptPanel.tsx` | Full manuscript text display with alignment-status colour coding |

### Alt-takes
| Component | Description |
|-----------|-------------|
| `AltTakesPanel.tsx` | Shows detected alternate-take clusters; lets the user play and compare takes |
| `AltTakeComparison.tsx` | Side-by-side waveform and score comparison for two alternate takes |

### Job & settings
| Component | Description |
|-----------|-------------|
| `JobStatus.tsx` | Inline progress bar showing current analysis stage and percentage |
| `JobStatusPopup.tsx` | Floating popup variant of the job status indicator |
| `TriageProgress.tsx` | Progress indicator specific to the LLM triage step |
| `SettingsPanel.tsx` | User-editable app settings form (detection thresholds, export format, etc.) |

### Modals & toasts
| Component | Description |
|-----------|-------------|
| `ConfirmModal.tsx` | Generic confirmation dialog (used before destructive actions) |
| `UndoToast.tsx` | Temporary toast notification with an undo action for dismissing issues |
| `KeyboardShortcutOverlay.tsx` | Full-screen overlay listing all keyboard shortcuts |

### ACX compliance
| Component | Description |
|-----------|-------------|
| `AcxPanel.tsx` | Displays ACX loudness and noise-floor check results with pass/fail indicators |
