import { CompositeScores, EditorialRecommendation, Issue, IssueStatus } from "../types"
import { formatTimecode, getConfidenceBand, getEditorStatusLabel, getEditorRecommendation, getIssueWhyFlagged, getRecommendationExplanation, getRecommendationHeroMeta, humanize, PRIORITY_COLORS } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"
import { useId, useState } from "react"
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
  const [showAdvanced, setShowAdvanced] = useState(false)
  const editorRec = getEditorRecommendation(recommendation?.model_action)
  const advancedPanelId = useId()
  return (
    <div className="scoring-panel" style={{ marginTop: 0 }}>
      <ScoreBar label="Mistake" score={scores.mistake_candidate?.score ?? 0} />
      <ScoreBar label="Pickup" score={scores.pickup_candidate?.score ?? 0} />
      <ScoreBar label="Continuity" score={scores.continuity_fit?.score ?? 0} />
      <ScoreBar label="Splice" score={scores.splice_readiness?.score ?? 0} />
      {recommendation ? (
        <div className="scoring-recommendation">
          <p style={{ margin: 0 }}>
            <strong>AI Recommendation:</strong>{" "}
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
        aria-expanded={showAdvanced}
        aria-controls={advancedPanelId}
      >
        {showAdvanced ? "Hide" : "Show"} Advanced Debug Scores
      </button>
      {showAdvanced ? (
        <div id={advancedPanelId} style={{ marginTop: 4, opacity: 0.7 }}>
          <ScoreBar label="Quality (debug)" score={scores.performance_quality?.score ?? 0} />
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

  const modelAction = issue.recommendation?.model_action ?? issue.model_action
  const effectiveModelAction = issue.alt_take_cluster_id != null ? "compare_takes" : modelAction
  const heroMeta = getRecommendationHeroMeta(effectiveModelAction)
  const whyFlagged = getIssueWhyFlagged(issue.type)
  const recExplanation = getRecommendationExplanation(effectiveModelAction)
  const confidenceBand = getConfidenceBand(issue.confidence)

  return (
    <CollapsibleSection
      title="Issue Detail"
      subtitle={humanize(issue.type)}
      storageKey="chapter-review:issue-detail"
    >
      {/* 1. Recommended action */}
      <div className={`issue-detail-rec-hero ${heroMeta.className}`}>
        <span className="rec-hero-icon" aria-hidden="true">{heroMeta.icon}</span>
        <span className="rec-hero-label">{heroMeta.label}</span>
      </div>

      {/* 2. Why it was flagged */}
      <p className="issue-detail-why">
        {whyFlagged}{recExplanation ? ` ${recExplanation}` : ""}
      </p>

      {/* 3. What the editor can do now */}
      <div className="row issue-detail-actions" aria-live="polite">
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

      {/* 4. Supporting evidence */}
      <div className="issue-detail-evidence">
        <div className="issue-detail-meta">
          <span className="pill">{formatIssueStatus(issue.status)}</span>
          {issue.alt_take_cluster_id != null || effectiveModelAction === "compare_takes" ? (
            <span className="pill pill-cluster" title="This issue is part of an alternate-take cluster">
              ⇄ Compare Takes
            </span>
          ) : null}
        </div>
        <div className="evidence-row">
          <span className="evidence-label">Expected</span>
          <span className="evidence-value">
            {issue.expected_text.trim() ? issue.expected_text : <span className="muted">None provided</span>}
          </span>
        </div>
        <div className="evidence-row">
          <span className="evidence-label">Spoken</span>
          <span className="evidence-value">
            {issue.spoken_text.trim() ? issue.spoken_text : <span className="muted">None captured</span>}
          </span>
        </div>
        <div className="evidence-row evidence-context">
          <span className="evidence-label">Context</span>
          <span className="evidence-value">
            {issue.context_before.trim() || issue.expected_text.trim() || issue.context_after.trim() ? (
              <>
                {issue.context_before.trim() ? <span className="muted">{issue.context_before} </span> : null}
                {issue.expected_text.trim() ? <mark className="evidence-highlight">{issue.expected_text}</mark> : null}
                {issue.context_after.trim() ? <span className="muted"> {issue.context_after}</span> : null}
              </>
            ) : (
              <span className="muted">No context provided</span>
            )}
          </span>
        </div>
      </div>

      {/* Note editor */}
      <NoteEditor issue={issue} onSaved={(updated) => onNoteUpdated?.(updated)} />

      {/* 5. Advanced technical details (collapsed) */}
      <CollapsibleSection
        title="Advanced Details"
        defaultCollapsed={true}
        storageKey="chapter-review:issue-detail-advanced"
        className="issue-detail-advanced"
      >
        <div className="issue-detail-meta">
          <span className={`pill ${confidenceBand.className}`}>{confidenceBand.label}</span>
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
        {issue.composite_scores ? (
          <ScoringBreakdown scores={issue.composite_scores} recommendation={issue.recommendation ?? undefined} />
        ) : null}
      </CollapsibleSection>
    </CollapsibleSection>
  )
}
