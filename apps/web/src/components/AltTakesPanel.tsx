import { useMemo, useState } from "react"
import { AltTakeCluster, Issue } from "../types"
import { formatTimecode } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"
import { AltTakeComparison } from "./AltTakeComparison"

type AltTakesPanelProps = {
  clusters: AltTakeCluster[]
  issues: Issue[]
  audioUrl: string | null
  onSelectPreferred: (clusterId: number, issueId: number) => Promise<void>
  onRejectTake: (issue: Issue) => Promise<void>
  onRestoreTake: (issue: Issue) => Promise<void>
  onSelectIssue: (issue: Issue) => void
}

export function AltTakesPanel({ clusters, issues, audioUrl, onSelectPreferred, onRejectTake, onRestoreTake, onSelectIssue }: AltTakesPanelProps) {
  const [compareClusterId, setCompareClusterId] = useState<number | null>(null)
  const compareCluster = useMemo(
    () => (compareClusterId != null ? clusters.find((c) => c.id === compareClusterId) ?? null : null),
    [clusters, compareClusterId]
  )

  if (clusters.length === 0) return null

  return (
    <>
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
            onRejectTake={onRejectTake}
            onRestoreTake={onRestoreTake}
            onSelectIssue={onSelectIssue}
            onCompare={() => setCompareClusterId(cluster.id)}
          />
        ))}
      </CollapsibleSection>
      {compareCluster ? (
        <AltTakeComparison
          cluster={compareCluster}
          issues={issues}
          audioUrl={audioUrl}
          onSelectPreferred={onSelectPreferred}
          onRejectTake={onRejectTake}
          onClose={() => setCompareClusterId(null)}
        />
      ) : null}
    </>
  )
}

function ClusterCard({
  cluster,
  issues,
  onSelectPreferred,
  onRejectTake,
  onRestoreTake,
  onSelectIssue,
  onCompare,
}: {
  cluster: AltTakeCluster
  issues: Issue[]
  onSelectPreferred: (clusterId: number, issueId: number) => Promise<void>
  onRejectTake: (issue: Issue) => Promise<void>
  onRestoreTake: (issue: Issue) => Promise<void>
  onSelectIssue: (issue: Issue) => void
  onCompare: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [saving, setSaving] = useState(false)
  const memberIssues = cluster.members
    .map((m) => {
      const issue = issues.find((i) => i.id === m.issue_id)
      return issue ? { issue, takeOrder: m.take_order } : null
    })
    .filter((entry): entry is { issue: Issue; takeOrder: number } => entry != null)
    .sort((a, b) => a.takeOrder - b.takeOrder)

  const activeTakes = memberIssues.filter(({ issue }) => issue.status !== "rejected")
  const rejectedTakes = memberIssues.filter(({ issue }) => issue.status === "rejected")

  const ranking = cluster.ranking

  return (
    <div className="alt-cluster-card">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="alt-cluster-header"
      >
        <span className="alt-cluster-title">
          {expanded ? "\u25bc" : "\u25b6"} "{cluster.manuscript_text.slice(0, 60)}
          {cluster.manuscript_text.length > 60 ? "..." : ""}"
        </span>
        <div className="alt-cluster-header-right">
          <span className="pill">{activeTakes.length} takes</span>
          <button
            type="button"
            className="alt-compare-open-btn"
            onClick={(e) => {
              e.stopPropagation()
              onCompare()
            }}
            title="Compare takes side by side"
          >
            Compare
          </button>
        </div>
      </button>
      {expanded ? (
        <div className="alt-cluster-body">
          {activeTakes.map(({ issue, takeOrder }) => {
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
                    {isPreferred ? "* " : ""}Take {takeOrder + 1}
                    {rankedTake ? ` (Rank #${rankedTake.rank})` : ""}
                  </span>
                  <span className="alt-take-time muted">
                    {formatTimecode(issue.start_ms)} - {formatTimecode(issue.end_ms)}
                  </span>
                </div>
                <div className="alt-take-spoken">
                  "{issue.spoken_text}"
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
                    <>
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
                      <button
                        type="button"
                        className="alt-take-reject-btn"
                        disabled={saving}
                        onClick={async (e) => {
                          e.stopPropagation()
                          setSaving(true)
                          try {
                            await onRejectTake(issue)
                          } finally {
                            setSaving(false)
                          }
                        }}
                        title="Mark for cut"
                      >
                        Cut
                      </button>
                    </>
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
          {rejectedTakes.length > 0 ? (
            <RejectedTakesSection
              takes={rejectedTakes}
              onRestore={onRestoreTake}
              saving={saving}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function RejectedTakesSection({
  takes,
  onRestore,
  saving,
}: {
  takes: { issue: Issue; takeOrder: number }[]
  onRestore: (issue: Issue) => Promise<void>
  saving: boolean
}) {
  const [shown, setShown] = useState(false)
  return (
    <div className="alt-rejected-section">
      <button type="button" className="alt-rejected-toggle" onClick={() => setShown(!shown)}>
        {shown ? "\u25bc" : "\u25b6"} {takes.length} cut take{takes.length === 1 ? "" : "s"}
      </button>
      {shown ? (
        <div className="alt-rejected-list">
          {takes.map(({ issue, takeOrder }) => (
            <div key={issue.id} className="alt-take-card rejected">
              <div className="alt-take-header">
                <span className="alt-take-title">Take {takeOrder + 1}</span>
                <span className="alt-take-time muted">
                  {formatTimecode(issue.start_ms)} - {formatTimecode(issue.end_ms)}
                </span>
              </div>
              <div className="alt-take-spoken">"{issue.spoken_text}"</div>
              <div className="alt-take-actions">
                <button
                  type="button"
                  className="alt-take-restore-btn"
                  disabled={saving}
                  onClick={(e) => {
                    e.stopPropagation()
                    void onRestore(issue)
                  }}
                >
                  Restore
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
