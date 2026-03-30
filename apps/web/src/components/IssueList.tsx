import type { CSSProperties, ReactNode } from "react"
import { Issue } from "../types"
import { ConfidenceFilter, getConfidenceBand, getIssueTypeMeta, humanize } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"

type IssueListProps = {
  issues: Issue[]
  selectedIssueId: number | null
  onSelect: (issue: Issue) => void
  searchQuery: string
  typeFilter: string
  confidenceFilter: ConfidenceFilter
}

export function IssueList({
  issues,
  selectedIssueId,
  onSelect,
  searchQuery,
  typeFilter,
  confidenceFilter
}: IssueListProps) {
  const normalizedSearch = searchQuery.trim().toLowerCase()
  const visibleIssues = issues.filter((issue) => {
    if (typeFilter !== "all" && issue.type !== typeFilter) {
      return false
    }

    if (!matchesConfidenceFilter(issue.confidence, confidenceFilter)) {
      return false
    }

    return normalizedSearch.length === 0 || issueMatchesSearch(issue, normalizedSearch)
  })

  return (
    <CollapsibleSection
      title="Issue List"
      subtitle={`${visibleIssues.length} matching issue${visibleIssues.length === 1 ? "" : "s"}`}
      storageKey="chapter-review:issue-list"
    >
      {visibleIssues.length === 0 ? (
        <p className="muted">No issues match the current search and filters.</p>
      ) : (
        <div className="list">
          {visibleIssues.map((issue) => {
            const isSelected = issue.id === selectedIssueId
            const typeMeta = getIssueTypeMeta(issue.type)
            const confidenceBand = getConfidenceBand(issue.confidence)

            return (
              <button
                key={issue.id}
                type="button"
                className={`list-item issue-card ${isSelected ? "selected" : ""}`}
                onClick={() => onSelect(issue)}
                aria-pressed={isSelected}
                aria-label={`${typeMeta.label} issue ${issue.id}`}
              >
                <div className="issue-card-row">
                  <div className="issue-card-meta">
                    <span className="issue-type-badge" style={{ "--issue-color": typeMeta.color } as CSSProperties}>
                      {typeMeta.label}
                    </span>
                    <span className={`issue-confidence-badge ${confidenceBand.className}`}>{confidenceBand.label}</span>
                  </div>
                  <span className="pill">{humanize(issue.status)}</span>
                </div>

                <div className="issue-card-text">
                  <span className="issue-card-field">
                    <strong>Expected:</strong> {renderHighlightedText(issue.expected_text, normalizedSearch)}
                  </span>
                  <span className="issue-card-field">
                    <strong>Spoken:</strong> {renderHighlightedText(issue.spoken_text, normalizedSearch)}
                  </span>
                </div>

                <div className="issue-card-context">
                  <span className="issue-card-field">
                    <strong>Before:</strong> {renderHighlightedText(issue.context_before, normalizedSearch)}
                  </span>
                  <span className="issue-card-field">
                    <strong>After:</strong> {renderHighlightedText(issue.context_after, normalizedSearch)}
                  </span>
                </div>

                {issue.note ? (
                  <div className="issue-card-note">
                    <span className="issue-card-field">
                      <strong>Note:</strong> {renderHighlightedText(issue.note, normalizedSearch)}
                    </span>
                  </div>
                ) : null}
              </button>
            )
          })}
        </div>
      )}
    </CollapsibleSection>
  )
}

function issueMatchesSearch(issue: Issue, search: string) {
  return [issue.spoken_text, issue.expected_text, issue.context_before, issue.context_after].some((value) =>
    value.toLowerCase().includes(search)
  )
}

function matchesConfidenceFilter(confidence: number, filter: ConfidenceFilter) {
  if (filter === "all") {
    return true
  }

  if (filter === "high") {
    return confidence >= 0.85
  }

  if (filter === "medium") {
    return confidence >= 0.65 && confidence < 0.85
  }

  return confidence < 0.65
}

function renderHighlightedText(value: string, search: string) {
  if (!value) {
    return <span className="muted">None provided.</span>
  }

  if (!search) {
    return value
  }

  const lowerValue = value.toLowerCase()
  const lowerSearch = search.toLowerCase()
  const parts: ReactNode[] = []
  let cursor = 0
  let matchIndex = lowerValue.indexOf(lowerSearch, cursor)

  while (matchIndex !== -1) {
    if (matchIndex > cursor) {
      parts.push(value.slice(cursor, matchIndex))
    }

    parts.push(
      <mark key={`${matchIndex}-${cursor}`}>{value.slice(matchIndex, matchIndex + lowerSearch.length)}</mark>
    )
    cursor = matchIndex + lowerSearch.length
    matchIndex = lowerValue.indexOf(lowerSearch, cursor)
  }

  if (cursor < value.length) {
    parts.push(value.slice(cursor))
  }

  return parts.length > 0 ? parts : value
}
