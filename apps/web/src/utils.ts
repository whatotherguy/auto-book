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
  return ISSUE_TYPE_META[type as IssueType] ?? { label: type, color: "#888" }
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
 */
export function getEditorRecommendation(modelAction: string | null | undefined): string {
  switch (modelAction) {
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
