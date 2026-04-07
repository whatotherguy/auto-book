import { CompositeScores, EditorialRecommendation, Issue, IssueStatus } from "../types"
import { formatTimecode, getConfidenceBand, getEditorStatusLabel, getEditorRecommendation, PRIORITY_COLORS } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"
import { useState } from "react"
import { updateIssue } from "../api"


function ScoreBar({ label, score }: { label: string; score: number }) {
  const filled = Math.round(score * 10)
  const bar_filled = "\u2588".repeat(filled)
  const bar_empty = "\u2591".repeat(10 - filled)
  return (
    <div className="score-bar">
      <span className="score-bar-label">{label}:</span>
      <span className="score-bar-value">{score.toFixed(2)}</span>
      <span className="score-bar-fill">{bar_filled}</span>
      <span className="score-bar-empty">{bar_empty}</span>
    </div>
  )
}

function ScoringBreakdown({ scores, recommendation }: { scores: CompositeScores; recommendation?: EditorialRecommendation }) {
  const [open, setOpen] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const editorRec = getEditorRecommendation(recommendation?.model_action)
  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="scoring-toggle"
      >
        {open ? "Hide" : "Show"} Scoring Details
      </button>
      {open ? (
        <div className="scoring-panel">
          <ScoreBar label="Mistake" score={scores.mistake_candidate?.score ?? 0} />
          <ScoreBar label="Pickup" score={scores.pickup_candidate?.score ?? 0} />
          <ScoreBar label="Continuity" score={scores.continuity_fit?.score ?? 0} />
          <ScoreBar label="Splice" score={scores.splice_readiness?.score ?? 0} />
          {recommendation ? (
            <div className="scoring-recommendation">
              <p style={{ margin: 0 }}>
                <strong>Recommendation:</strong>{" "}
                <span style={{ color: PRIORITY_COLORS[recommendation.priority] ?? "inherit" }}>
                  {editorRec || recommendation.action} ({recommendation.priority})
                </span>
              </p>
              <p className="muted" style={{ margin: "2px 0 0", fontSize: "0.85em" }}>{recommendation.reasoning}</p>
              {scores.mistake_candidate?.ambiguity_flags?.length ? (
                <p className="scoring-ambiguity">
                  Ambiguity: {scores.mistake_candidate.ambiguity_flags.join("; ")}
                </p>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="scoring-toggle"
            style={{ marginTop: 8, fontSize: "0.85em" }}
          >
            {showAdvanced ? "Hide" : "Show"} Advanced Debug Scores
          </button>
          {showAdvanced ? (
            <div style={{ marginTop: 4, opacity: 0.7 }}>
              <ScoreBar label="Quality (debug)" score={scores.performance_quality?.score ?? 0} />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function NoteEditor({ issue, onSaved }: { issue: Issue; onSaved: (updated: Issue) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(issue.note ?? "")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  async function handleSave() {
    try {
      setSaving(true)
      setSaveError(null)
      const updated = await updateIssue(issue.id, { note: draft.trim() || undefined })
      onSaved(updated)
      setEditing(false)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save note.")
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div className="note-editor">
        <label><strong>Note:</strong></label>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a note about this issue..."
          rows={3}
        />
        {saveError ? <p className="muted" style={{ color: "var(--color-error, #f87171)", margin: "4px 0 0" }}>{saveError}</p> : null}
        <div className="note-editor-actions">
          <button type="button" className="approve-button" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Saving..." : "Save Note"}
          </button>
          <button type="button" onClick={() => { setEditing(false); setDraft(issue.note ?? ""); setSaveError(null) }}>
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="note-display">
      <p style={{ margin: 0, flex: 1 }}>
        <strong>Note:</strong> {issue.note || <span className="muted">No note yet.</span>}
      </p>
      <button type="button" className="note-edit-trigger" onClick={() => { setDraft(issue.note ?? ""); setEditing(true) }}>
        {issue.note ? "Edit" : "Add note"}
      </button>
    </div>
  )
}

function formatIssueType(type: string) {
  return type
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

function formatIssueStatus(status: string) {
  return getEditorStatusLabel(status)
}

export function IssueDetail({
  issue,
  onStatusChange,
  onNoteUpdated,
}: {
  issue: Issue | null
  onStatusChange: (issue: Issue, status: IssueStatus) => Promise<void>
  onNoteUpdated?: (updated: Issue) => void
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
    if (!issue) return
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
      <NoteEditor issue={issue} onSaved={(updated) => onNoteUpdated?.(updated)} />
      {issue.composite_scores ? (
        <ScoringBreakdown scores={issue.composite_scores} recommendation={issue.recommendation ?? undefined} />
      ) : null}
      <div className="row" aria-live="polite" style={{ marginTop: 12 }}>
        <button className="approve-button" onClick={() => void setStatus("approved")} disabled={isSaving || issue.status === "approved"}>
          {isSaving && issue.status !== "approved" ? "Saving…" : "Keep"}
        </button>
        <button className="reject-button" onClick={() => void setStatus("rejected")} disabled={isSaving || issue.status === "rejected"}>
          Cut
        </button>
        <button className="manual-button" onClick={() => void setStatus("needs_manual")} disabled={isSaving || issue.status === "needs_manual"}>
          Needs Review
        </button>
      </div>
    </CollapsibleSection>
  )
}
