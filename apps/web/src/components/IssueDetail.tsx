import { Issue, IssueStatus } from "../types"
import { formatTimecode, getConfidenceBand } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"
import { useState } from "react"

function formatIssueType(type: string) {
  return type
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

function formatIssueStatus(status: string) {
  switch (status) {
    case "needs_manual":
      return "Needs Manual Review"
    default:
      return formatIssueType(status)
  }
}

export function IssueDetail({
  issue,
  onStatusChange
}: {
  issue: Issue | null
  onStatusChange: (issue: Issue, status: IssueStatus) => Promise<void>
}) {
  const [isSaving, setIsSaving] = useState(false)

  if (!issue) {
    return (
      <CollapsibleSection
        title="Issue Detail"
        defaultCollapsed={false}
        storageKey="chapter-review:issue-detail"
      >
        <p className="muted">Select an issue to review its timing, transcript context, and decision controls.</p>
      </CollapsibleSection>
    )
  }

  async function setStatus(status: IssueStatus) {
    try {
      setIsSaving(true)
      await onStatusChange(issue, status)
    } finally {
      setIsSaving(false)
    }
  }

  const confidenceBand = getConfidenceBand(issue.confidence)

  return (
    <CollapsibleSection
      title="Issue Detail"
      subtitle={formatIssueType(issue.type)}
      storageKey="chapter-review:issue-detail"
    >
      <div className="issue-detail-meta">
        <span className={`pill ${confidenceBand.className}`}>{confidenceBand.label}</span>
        <span className="pill">{formatIssueStatus(issue.status)}</span>
        <span className="pill">
          {formatTimecode(issue.start_ms)} to {formatTimecode(issue.end_ms)}
        </span>
      </div>
      <p><strong>Confidence Score:</strong> {issue.confidence.toFixed(2)}</p>
      {issue.triage_verdict ? (
        <p>
          <strong>AI Triage:</strong>{" "}
          <span className={`issue-triage-badge ${issue.triage_verdict}`}>
            {issue.triage_verdict === "dismiss" ? "Likely false positive" : issue.triage_verdict === "keep" ? "Likely real issue" : "Needs manual review"}
          </span>
          {issue.triage_reason ? <span className="muted"> — {issue.triage_reason}</span> : null}
        </p>
      ) : null}
      <p><strong>Expected Text:</strong> {issue.expected_text || "None provided."}</p>
      <p><strong>Spoken Text:</strong> {issue.spoken_text || "None captured."}</p>
      <p><strong>Context Before:</strong> {issue.context_before || "None available."}</p>
      <p><strong>Context After:</strong> {issue.context_after || "None available."}</p>
      {issue.note ? <p><strong>Note:</strong> {issue.note}</p> : null}
      <div className="row" aria-live="polite">
        <button onClick={() => void setStatus("approved")} disabled={isSaving || issue.status === "approved"}>
          {isSaving && issue.status !== "approved" ? "Saving…" : "Approve Issue"}
        </button>
        <button onClick={() => void setStatus("rejected")} disabled={isSaving || issue.status === "rejected"}>
          Reject Issue
        </button>
        <button onClick={() => void setStatus("needs_manual")} disabled={isSaving || issue.status === "needs_manual"}>
          Mark for Manual Review
        </button>
      </div>
    </CollapsibleSection>
  )
}
