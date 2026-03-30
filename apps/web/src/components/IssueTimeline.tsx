import { Issue } from "../types"
import { getConfidenceBand, getIssueTypeMeta, humanize, ISSUE_TYPE_META } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"
import type { CSSProperties } from "react"

function formatTimelineLabel(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor(totalSeconds / 60) % 60
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`
  }

  return `${minutes}:${seconds.toString().padStart(2, "0")}`
}

export function IssueTimeline({
  issues,
  selectedIssueId,
  durationMs,
  onSelect,
  playheadMs = 0,
}: {
  issues: Issue[]
  selectedIssueId: number | null
  durationMs: number
  onSelect: (issue: Issue) => void
  playheadMs?: number
}) {
  const safeDurationMs = Math.max(
    durationMs,
    issues.reduce((max, issue) => Math.max(max, issue.end_ms, issue.start_ms + 1), 1)
  )

  return (
    <CollapsibleSection
      title="Chapter Timeline"
      subtitle="Track-level map of review issues and suggested cut ranges."
      className="timeline-shell"
      storageKey="chapter-review:timeline"
      actions={
        <div className="timeline-meta">
          <span>{issues.length} issues</span>
          <span>{formatTimelineLabel(safeDurationMs)}</span>
        </div>
      }
    >
      <div className="timeline-track">
        <div className="timeline-ruler" aria-hidden="true">
          <span>0:00</span>
          <span>{formatTimelineLabel(Math.floor(safeDurationMs / 2))}</span>
          <span>{formatTimelineLabel(safeDurationMs)}</span>
        </div>

        <div className="timeline-lane" role="list" aria-label="Issue timeline markers">
          <div className="timeline-waveform-backdrop" />
          {playheadMs > 0 && safeDurationMs > 0 ? (
            <div
              className="timeline-playhead"
              style={{ left: `${Math.min(100, (playheadMs / safeDurationMs) * 100)}%` }}
            />
          ) : null}
          {issues.map((issue) => {
            const startPercent = Math.max(0, Math.min(100, (issue.start_ms / safeDurationMs) * 100))
            const endPercent = Math.max(startPercent, Math.min(100, (issue.end_ms / safeDurationMs) * 100))
            const widthPercent = Math.max(endPercent - startPercent, 0.35)
            const isSelected = issue.id === selectedIssueId
            const issueTypeMeta = getIssueTypeMeta(issue.type)
            const confidenceBand = getConfidenceBand(issue.confidence)
            const confidenceLabel = confidenceBand.label.replace(" Confidence", "")
            const ariaLabel = `${issueTypeMeta.label} from ${formatTimelineLabel(issue.start_ms)} to ${formatTimelineLabel(
              issue.end_ms
            )}. Confidence ${Math.round(issue.confidence * 100)} percent (${confidenceLabel}). ${humanize(issue.status)}.`

            return (
              <button
                key={issue.id}
                type="button"
                role="listitem"
                className={`timeline-issue ${isSelected ? "selected" : ""}`}
                style={
                  {
                    left: `${startPercent}%`,
                    width: `${widthPercent}%`,
                    "--issue-color": issueTypeMeta.color
                  } as CSSProperties
                }
                onClick={() => onSelect(issue)}
                aria-pressed={isSelected}
                aria-label={ariaLabel}
                title={`${issueTypeMeta.label} - ${formatTimelineLabel(issue.start_ms)} to ${formatTimelineLabel(issue.end_ms)}`}
              >
                <span className="timeline-edge start" />
                <span className="timeline-region" />
                <span className="timeline-edge end" />
              </button>
            )
          })}
        </div>

        <div className="timeline-legend" aria-label="Issue type legend">
          {Object.entries(ISSUE_TYPE_META).map(([type, meta]) => (
            <span key={type}>
              <i style={{ background: meta.color }} />
              {meta.label}
            </span>
          ))}
        </div>
      </div>
    </CollapsibleSection>
  )
}
