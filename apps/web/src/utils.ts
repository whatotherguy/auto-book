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
  false_start: { label: "False Start", color: "#7c3aed" },
  repetition: { label: "Repetition", color: "#d97706" },
  pickup_restart: { label: "Pickup Restart", color: "#2563eb" },
  substitution: { label: "Substitution", color: "#0f766e" },
  missing_text: { label: "Missing Text", color: "#dc2626" },
  long_pause: { label: "Long Pause", color: "#14b8a6" },
  uncertain_alignment: { label: "Uncertain Alignment", color: "#6b7280" }
} as const satisfies Record<string, { label: string; color: string }>

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
