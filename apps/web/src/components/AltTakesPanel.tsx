import { useState } from "react"
import { AltTakeCluster, Issue } from "../types"
import { formatTimecode } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"

type AltTakesPanelProps = {
  clusters: AltTakeCluster[]
  issues: Issue[]
  onSelectPreferred: (clusterId: number, issueId: number) => Promise<void>
  onSelectIssue: (issue: Issue) => void
}

export function AltTakesPanel({ clusters, issues, onSelectPreferred, onSelectIssue }: AltTakesPanelProps) {
  if (clusters.length === 0) return null

  return (
    <CollapsibleSection
      title="Alternate Takes"
      subtitle={`${clusters.length} cluster${clusters.length === 1 ? "" : "s"}`}
      storageKey="chapter-review:alt-takes"
    >
      {clusters.map((cluster) => (
        <ClusterCard
          key={cluster.id}
          cluster={cluster}
          issues={issues}
          onSelectPreferred={onSelectPreferred}
          onSelectIssue={onSelectIssue}
        />
      ))}
    </CollapsibleSection>
  )
}

function ClusterCard({
  cluster,
  issues,
  onSelectPreferred,
  onSelectIssue,
}: {
  cluster: AltTakeCluster
  issues: Issue[]
  onSelectPreferred: (clusterId: number, issueId: number) => Promise<void>
  onSelectIssue: (issue: Issue) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [saving, setSaving] = useState(false)
  const memberIssues = cluster.members
    .map((m) => issues.find((i) => i.id === m.issue_id))
    .filter((i): i is Issue => i != null)
    .sort((a, b) => a.start_ms - b.start_ms)

  const ranking = cluster.ranking

  return (
    <div className="alt-cluster-card">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="alt-cluster-header"
      >
        <span className="alt-cluster-title">
          {expanded ? "\u25bc" : "\u25b6"} {cluster.manuscript_text.slice(0, 60)}
          {cluster.manuscript_text.length > 60 ? "..." : ""}
        </span>
        <span className="pill">{cluster.members.length} takes</span>
      </button>
      {expanded ? (
        <div className="alt-cluster-body">
          {memberIssues.map((issue, idx) => {
            const isPreferred = cluster.preferred_issue_id === issue.id
            const rankedTake = ranking?.ranked_takes?.find((t) => t.issue_id === issue.id)
            return (
              <div
                key={issue.id}
                className={`alt-take-card${isPreferred ? " preferred" : ""}`}
                onClick={() => onSelectIssue(issue)}
              >
                <div className="alt-take-header">
                  <span className="alt-take-title">
                    {isPreferred ? "* " : ""}Take {idx + 1}
                    {rankedTake ? ` (Rank #${rankedTake.rank})` : ""}
                  </span>
                  <span className="alt-take-time">
                    {formatTimecode(issue.start_ms)} - {formatTimecode(issue.end_ms)}
                  </span>
                </div>
                {rankedTake ? (
                  <div className="alt-take-scores">
                    Quality: {rankedTake.performance_quality.toFixed(2)} &middot;
                    Fit: {rankedTake.continuity_fit.toFixed(2)} &middot;
                    Text: {rankedTake.text_accuracy.toFixed(2)} &middot;
                    Score: {rankedTake.total_score.toFixed(2)}
                  </div>
                ) : null}
                {issue.prosody_features ? (
                  <div className="alt-take-prosody">
                    Rate: {issue.prosody_features.speech_rate_wps.toFixed(1)} wps
                    {issue.prosody_features.f0_mean_hz != null ? ` \u00b7 Pitch: ${Math.round(issue.prosody_features.f0_mean_hz)} Hz` : ""}
                  </div>
                ) : null}
                <div className="alt-take-actions">
                  {!isPreferred ? (
                    <button
                      type="button"
                      disabled={saving}
                      onClick={async (e) => {
                        e.stopPropagation()
                        setSaving(true)
                        try {
                          await onSelectPreferred(cluster.id, issue.id)
                        } finally {
                          setSaving(false)
                        }
                      }}
                    >
                      Select as preferred
                    </button>
                  ) : (
                    <span className="alt-take-preferred-label">Preferred take</span>
                  )}
                </div>
              </div>
            )
          })}
          {ranking?.selection_reasons?.length ? (
            <div className="alt-cluster-selection">
              Selection: {ranking.selection_reasons.join(", ")}
              {ranking.confidence < 0.6 ? " (close call)" : ""}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
