import { humanize } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"

export function JobStatus({
  title = "Analysis Status",
  storageKey = "chapter-review:analysis-status",
  status,
  progress,
  step,
  errorMessage
}: {
  title?: string
  storageKey?: string
  status: string
  progress?: number
  step?: string | null
  errorMessage?: string | null
}) {
  const normalizedStatus = status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")

  return (
    <CollapsibleSection
      title={title}
      subtitle={normalizedStatus}
      className="status-card"
      storageKey={storageKey}
      actions={typeof progress === "number" ? <div className="status-progress-label">{progress}%</div> : null}
    >
      <div className="status-header">
        <div>
          <strong className="status-value">{normalizedStatus}</strong>
        </div>
      </div>
      {typeof progress === "number" ? (
        <div className="status-progress-bar">
          <div className="status-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      ) : null}
      {step ? <div className="status-step">Current Step: {humanize(step)}</div> : null}
      {errorMessage ? <div className="error-text">{errorMessage}</div> : null}
    </CollapsibleSection>
  )
}
