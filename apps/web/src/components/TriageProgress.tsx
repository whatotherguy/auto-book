import { useMemo } from "react"
import { Issue } from "../types"

export function TriageProgress({ issues }: { issues: Issue[] }) {
  const counts = useMemo(() => {
    let approved = 0
    let rejected = 0
    let pending = 0
    for (const issue of issues) {
      if (issue.status === "approved") approved++
      else if (issue.status === "rejected") rejected++
      else pending++
    }
    return { approved, rejected, pending, total: issues.length }
  }, [issues])

  if (counts.total === 0) return null

  const reviewed = counts.approved + counts.rejected
  const pct = Math.round((reviewed / counts.total) * 100)

  return (
    <div className="triage-progress">
      <div className="triage-progress-bar">
        {counts.approved > 0 ? (
          <div
            className="triage-progress-fill approved"
            style={{ width: `${(counts.approved / counts.total) * 100}%` }}
            title={`${counts.approved} approved`}
          />
        ) : null}
        {counts.rejected > 0 ? (
          <div
            className="triage-progress-fill rejected"
            style={{ width: `${(counts.rejected / counts.total) * 100}%` }}
            title={`${counts.rejected} rejected`}
          />
        ) : null}
      </div>
      <div className="triage-progress-labels">
        <span className="triage-stat">
          <span className="triage-dot approved" /> {counts.approved} approved
        </span>
        <span className="triage-stat">
          <span className="triage-dot rejected" /> {counts.rejected} rejected
        </span>
        <span className="triage-stat">
          <span className="triage-dot pending" /> {counts.pending} pending
        </span>
        <span className="triage-stat triage-pct">{reviewed}/{counts.total} reviewed ({pct}%)</span>
      </div>
    </div>
  )
}
