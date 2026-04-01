import { useEffect, useRef, useState } from "react"
import { humanize } from "../utils"

const ACTIVE_STATUSES = new Set(["queued", "running", "uploading"])

export function JobStatusPopup({
  title = "Analysis Status",
  status,
  progress,
  step,
  errorMessage,
}: {
  title?: string
  status: string
  progress?: number
  step?: string | null
  errorMessage?: string | null
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const prevActiveRef = useRef(false)

  const isActive = ACTIVE_STATUSES.has(status)

  useEffect(() => {
    if (isActive && !prevActiveRef.current) {
      setDismissed(false)
      setCollapsed(false)
    }
    prevActiveRef.current = isActive
  }, [isActive])

  if (dismissed) return null

  const normalizedStatus = status
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ")

  if (collapsed) {
    return (
      <div className="job-popup job-popup-collapsed">
        <div className="job-popup-mini">
          <span className="job-popup-mini-title">{title}</span>
          {typeof progress === "number" ? (
            <div className="job-popup-mini-bar">
              <div className="status-progress-fill" style={{ width: `${progress}%` }} />
            </div>
          ) : null}
          {typeof progress === "number" ? (
            <span className="job-popup-mini-pct">{progress}%</span>
          ) : null}
          <button
            type="button"
            className="job-popup-btn"
            onClick={() => setCollapsed(false)}
            aria-label="Expand"
          >
            ▲
          </button>
          <button
            type="button"
            className="job-popup-btn"
            onClick={() => setDismissed(true)}
            aria-label="Close"
          >
            ×
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="job-popup">
      <div className="job-popup-header">
        <div className="job-popup-header-info">
          <span className="job-popup-title">{title}</span>
          <span className="job-popup-status">{normalizedStatus}</span>
        </div>
        <div className="job-popup-header-btns">
          {typeof progress === "number" ? (
            <span className="job-popup-progress-label">{progress}%</span>
          ) : null}
          <button
            type="button"
            className="job-popup-btn"
            onClick={() => setCollapsed(true)}
            aria-label="Collapse"
          >
            ▼
          </button>
          <button
            type="button"
            className="job-popup-btn"
            onClick={() => setDismissed(true)}
            aria-label="Close"
          >
            ×
          </button>
        </div>
      </div>
      {typeof progress === "number" ? (
        <div className="status-progress-bar">
          <div className="status-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      ) : null}
      {step ? <div className="status-step">Current Step: {humanize(step)}</div> : null}
      {errorMessage ? <div className="error-text">{errorMessage}</div> : null}
    </div>
  )
}
