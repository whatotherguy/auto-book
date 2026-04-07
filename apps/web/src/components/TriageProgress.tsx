import { useMemo } from "react"
import { Issue } from "../types"

export function TriageProgress({ issues }: { issues: Issue[] }) {
  const counts = useMemo(() => {
    let kept = 0
    let cut = 0
    let pending = 0
    for (const issue of issues) {
      if (issue.status === "approved") kept++
      else if (issue.status === "rejected") cut++
      else pending++
    }
    return { kept, cut, pending, total: issues.length }
  }, [issues])

  if (counts.total === 0) return null

  const reviewed = counts.kept + counts.cut
  const pct = Math.round((reviewed / counts.total) * 100)

  return (
    <div className="triage-progress">
      <div className="triage-progress-bar">
        {counts.kept > 0 ? (
          <div
            className="triage-progress-fill kept"
            style={{ width: `${(counts.kept / counts.total) * 100}%` }}
            title={`${counts.kept} kept`}
          />
        ) : null}
        {counts.cut > 0 ? (
          <div
            className="triage-progress-fill cut"
            style={{ width: `${(counts.cut / counts.total) * 100}%` }}
            title={`${counts.cut} cut`}
          />
        ) : null}
      </div>
      <div className="triage-progress-labels">
        <span className="triage-stat">
          <span className="triage-dot kept" /> {counts.kept} kept
        </span>
        <span className="triage-stat">
          <span className="triage-dot cut" /> {counts.cut} cut
        </span>
        <span className="triage-stat">
          <span className="triage-dot pending" /> {counts.pending} unreviewed
        </span>
        <span className="triage-stat triage-pct">{reviewed}/{counts.total} reviewed ({pct}%)</span>
      </div>
    </div>
  )
}
