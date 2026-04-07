export function formatTimecode(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) ms = 0
  const totalSeconds = Math.floor(ms / 1000)
  const millis = ms % 1000
  const seconds = totalSeconds % 60
  const minutes = Math.floor(totalSeconds / 60) % 60
  const hours = Math.floor(totalSeconds / 3600)

  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}.${millis.toString().padStart(3, "0")}`
}

export function humanize(value: string): string {
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export const ISSUE_TYPE_META = {
  false_start: { label: "False Start", color: "#7c3aed", icon: "" },
  repetition: { label: "Repetition", color: "#d97706", icon: "" },
  pickup_restart: { label: "Pickup Restart", color: "#2563eb", icon: "" },
  substitution: { label: "Substitution", color: "#0f766e", icon: "" },
  missing_text: { label: "Missing Text", color: "#dc2626", icon: "" },
  long_pause: { label: "Long Pause", color: "#14b8a6", icon: "" },
  uncertain_alignment: { label: "Uncertain Alignment", color: "#6b7280", icon: "" },
  pickup_candidate: { label: "Pickup Candidate", color: "#5B8DEF", icon: "\u21a9" },
  alt_take: { label: "Alternate Take", color: "#9B59B6", icon: "\u21c4" },
  performance_variant: { label: "Performance Variant", color: "#E67E22", icon: "\u266a" },
  non_speech_marker: { label: "Non-Speech Marker", color: "#95A5A6", icon: "\u25cf" },
} as const satisfies Record<string, { label: string; color: string; icon: string }>

export const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
}

export const PRIORITY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#f97316",
  medium: "#eab308",
  low: "#6b7280",
  info: "transparent",
}

export type IssueType = keyof typeof ISSUE_TYPE_META

export function getIssueTypeMeta(type: string) {
  return ISSUE_TYPE_META[type as IssueType] ?? { label: type, color: "#888", icon: "" }
}

export type ConfidenceBand = {
  label: string
  className: string
}

export type ConfidenceFilter = "all" | "high" | "medium" | "low"

export function getConfidenceBand(confidence: number): ConfidenceBand {
  if (confidence >= 0.85) {
    return { label: "High Confidence", className: "confidence-high" }
  }

  if (confidence >= 0.65) {
    return { label: "Medium Confidence", className: "confidence-medium" }
  }

  return { label: "Low Confidence", className: "confidence-low" }
}

/**
 * Translate legacy issue status to editor-facing label
 */
export function getEditorStatusLabel(status: string): string {
  switch (status) {
    case "approved":
      return "Keep"
    case "rejected":
      return "Cut"
    case "needs_manual":
      return "Needs Review"
    case "pending":
      return "Unreviewed"
    default:
      return humanize(status)
  }
}

/**
 * Translate model_action to editor-facing recommendation label
 * @param model_action - The model action value from Issue.model_action (snake_case field)
 */
export function getEditorRecommendation(model_action: string | null | undefined): string {
  switch (model_action) {
    case "safe_cut":
      return "Recommended: Cut"
    case "ignore":
      return "Recommended: Keep"
    case "compare_takes":
      return "Compare Takes"
    case "review":
      return "Needs Review"
    default:
      return ""
  }
}

/**
 * Plain-language explanation of why an issue type was flagged, for the editor.
 */
export function getIssueWhyFlagged(type: string): string {
  switch (type) {
    case "false_start":
      return "The narrator started a phrase and restarted before completing it."
    case "repetition":
      return "A word or phrase was said more than once."
    case "pickup_restart":
      return "The narrator restarted a phrase — likely re-reading after a stumble."
    case "substitution":
      return "A word doesn't match the manuscript — it may need to be re-read."
    case "missing_text":
      return "Text from the manuscript appears to have been skipped."
    case "long_pause":
      return "An unusually long pause was detected in the narration."
    case "uncertain_alignment":
      return "The transcript couldn't be reliably matched to the manuscript here."
    case "pickup_candidate":
      return "This may be a pickup take intended to replace a prior issue."
    case "alt_take":
      return "Multiple takes of this passage were detected."
    case "performance_variant":
      return "The narration differs from the manuscript in phrasing or delivery."
    case "non_speech_marker":
      return "A non-speech sound or signal marker was detected."
    default:
      return "This passage was flagged for editorial review."
  }
}

/**
 * Plain-language explanation of the model recommendation, for the editor.
 */
export function getRecommendationExplanation(model_action: string | null | undefined): string {
  switch (model_action) {
    case "safe_cut":
      return "This looks like a clear mistake — safe to cut."
    case "ignore":
      return "This is likely fine. No cut needed."
    case "compare_takes":
      return "Multiple takes exist for this passage. Listen and pick the best one."
    case "review":
      return "This needs a judgment call. Listen before deciding."
    default:
      return ""
  }
}

export type RecommendationHeroMeta = {
  label: string
  icon: string
  className: string
}

/**
 * Get display metadata for the recommendation hero badge in the issue detail panel.
 */
export function getRecommendationHeroMeta(model_action: string | null | undefined): RecommendationHeroMeta {
  const label = getEditorRecommendation(model_action) || "Needs Review"
  switch (model_action) {
    case "safe_cut":
      return { label, icon: "✂", className: "rec-hero-cut" }
    case "ignore":
      return { label, icon: "✓", className: "rec-hero-keep" }
    case "compare_takes":
      return { label, icon: "⇄", className: "rec-hero-compare" }
    default:
      return { label, icon: "?", className: "rec-hero-review" }
  }
}

// ---------------------------------------------------------------------------
// UI Bucket grouping
// ---------------------------------------------------------------------------

export type UIBucket = "ready_to_cut" | "compare_takes" | "needs_review" | "probably_keep" | "low_priority"

export type UIBucketMeta = {
  label: string
  icon: string
  description: string
}

export const UI_BUCKET_META: Record<UIBucket, UIBucketMeta> = {
  ready_to_cut: {
    label: "Ready to Cut",
    icon: "✂",
    description: "High-confidence mistakes — safe to remove",
  },
  compare_takes: {
    label: "Compare Takes",
    icon: "⇄",
    description: "Multiple takes detected — choose the best one",
  },
  needs_review: {
    label: "Needs Review",
    icon: "?",
    description: "Requires editorial judgment before deciding",
  },
  probably_keep: {
    label: "Probably Keep",
    icon: "✓",
    description: "Likely acceptable — low priority, but worth a listen",
  },
  low_priority: {
    label: "Low-Priority Markers",
    icon: "○",
    description: "Signal-only markers and weak-evidence items — review last",
  },
}

export const BUCKET_ORDER: UIBucket[] = [
  "ready_to_cut",
  "compare_takes",
  "needs_review",
  "probably_keep",
  "low_priority",
]

/**
 * Assign an issue to an editorial UI bucket based on model_action and evidence quality.
 *
 * Rules (evaluated in order):
 * 1. non_speech_marker type → Low-Priority Markers (always)
 * 2. model_action "safe_cut"      → Ready to Cut
 * 3. model_action "compare_takes" → Compare Takes
 * 4. model_action "review"        → Needs Review
 * 5. model_action "ignore"        → Probably Keep
 * 6. No model_action + confidence < 0.65 → Low-Priority Markers
 * 7. Default (no model_action, confidence ≥ 0.65) → Needs Review
 */
export function getUIBucket(issue: { type: string; model_action?: import("./types").ModelAction | null; confidence: number }): UIBucket {
  if (issue.type === "non_speech_marker") return "low_priority"
  if (issue.model_action === "safe_cut") return "ready_to_cut"
  if (issue.model_action === "compare_takes") return "compare_takes"
  if (issue.model_action === "review") return "needs_review"
  if (issue.model_action === "ignore") return "probably_keep"
  if (issue.confidence < 0.65) return "low_priority"
  return "needs_review"
}
