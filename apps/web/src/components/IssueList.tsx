import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { Issue } from "../types"
import { ConfidenceFilter, getConfidenceBand, getEditorStatusLabel, getEditorRecommendation, getIssueTypeMeta, PRIORITY_COLORS, PRIORITY_ORDER } from "../utils"
import { CollapsibleSection } from "./CollapsibleSection"
import { SkeletonIssueList } from "./Skeleton"

type IssueListProps = {
  issues: Issue[]
  selectedIssueId: number | null
  onSelect: (issue: Issue) => void
  searchQuery: string
  enabledTypes: Set<string> | "all"
  confidenceFilter: ConfidenceFilter
  loading?: boolean
}

export function IssueList({
  issues,
  selectedIssueId,
  onSelect,
  searchQuery,
  enabledTypes,
  confidenceFilter,
  loading = false,
}: IssueListProps) {
  const [sortBy, setSortBy] = useState<"time" | "confidence" | "type" | "priority">("priority")
  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)
  const normalizedSearch = searchQuery.trim().toLowerCase()

  const visibleIssues = useMemo(() => issues.filter((issue) => {
    if (enabledTypes !== "all" && !enabledTypes.has(issue.type)) {
      return false
    }

    if (!matchesConfidenceFilter(issue.confidence, confidenceFilter)) {
      return false
    }

    return normalizedSearch.length === 0 || issueMatchesSearch(issue, normalizedSearch)
  }), [issues, enabledTypes, confidenceFilter, normalizedSearch])

  const sortedIssues = useMemo(() => {
    const sorted = [...visibleIssues]
    if (sortBy === "priority") {
      sorted.sort((a, b) => {
        const pa = PRIORITY_ORDER[a.recommendation?.priority ?? "info"] ?? 4
        const pb = PRIORITY_ORDER[b.recommendation?.priority ?? "info"] ?? 4
        if (pa !== pb) return pa - pb
        const ma = a.composite_scores?.mistake_candidate?.score ?? 0
        const mb = b.composite_scores?.mistake_candidate?.score ?? 0
        if (ma !== mb) return mb - ma
        const pua = a.composite_scores?.pickup_candidate?.score ?? 0
        const pub = b.composite_scores?.pickup_candidate?.score ?? 0
        return pub - pua
      })
    } else if (sortBy === "confidence") {
      sorted.sort((a, b) => b.confidence - a.confidence)
    } else if (sortBy === "type") {
      sorted.sort((a, b) => a.type.localeCompare(b.type) || a.start_ms - b.start_ms)
    } else {
      sorted.sort((a, b) => a.start_ms - b.start_ms)
    }
    return sorted
  }, [visibleIssues, sortBy])

  const updateScrollButtons = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 2)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateScrollButtons()
    el.addEventListener("scroll", updateScrollButtons, { passive: true })
    const ro = new ResizeObserver(updateScrollButtons)
    ro.observe(el)
    return () => {
      el.removeEventListener("scroll", updateScrollButtons)
      ro.disconnect()
    }
  }, [updateScrollButtons, sortedIssues.length])

  function scrollBy(direction: -1 | 1) {
    const el = scrollRef.current
    if (!el) return
    el.scrollBy({ left: direction * 300, behavior: "smooth" })
  }

  // Auto-scroll selected issue into view
  useEffect(() => {
    if (selectedIssueId == null) return
    const el = document.querySelector(`.issue-card[aria-pressed="true"]`)
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" })
    }
  }, [selectedIssueId])

  return (
    <CollapsibleSection
      title="Issue List"
      subtitle={`${visibleIssues.length} matching issue${visibleIssues.length === 1 ? "" : "s"}`}
      storageKey="chapter-review:issue-list"
      actions={
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "time" | "confidence" | "type" | "priority")}
          className="issue-sort-select"
        >
          <option value="priority">Priority</option>
          <option value="time">Time</option>
          <option value="confidence">Confidence</option>
          <option value="type">Type</option>
        </select>
      }
    >
      {loading ? (
        <SkeletonIssueList count={5} />
      ) : sortedIssues.length === 0 ? (
        <p className="muted">No issues match the current search and filters.</p>
      ) : (
        <div className="issue-list-scroll-wrapper">
          {canScrollLeft ? (
            <button type="button" className="issue-scroll-btn issue-scroll-left" onClick={() => scrollBy(-1)} aria-label="Scroll left">
              &lsaquo;
            </button>
          ) : null}
          <div className="issue-list-horizontal" ref={scrollRef}>
            {sortedIssues.map((issue) => {
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
                      {issue.recommendation?.priority && issue.recommendation.priority !== "info" ? (
                        <span
                          className="priority-dot"
                          style={{ background: PRIORITY_COLORS[issue.recommendation.priority] ?? "transparent" }}
                          title={`Priority: ${issue.recommendation.priority}`}
                        />
                      ) : null}
                      <span className="issue-type-badge" style={{ "--issue-color": typeMeta.color } as CSSProperties}>
                        {(typeMeta as any).icon ? `${(typeMeta as any).icon} ` : ""}{typeMeta.label}
                      </span>
                      <span className={`issue-confidence-badge ${confidenceBand.className}`}>{confidenceBand.label}</span>
                    </div>
                    <span className="pill">{getEditorStatusLabel(issue.status)}</span>
                  </div>

                  {/* Editor recommendation based on model action */}
                  {issue.model_action ? (
                    <div className="issue-card-meta">
                      <span className="issue-recommendation-badge">{getEditorRecommendation(issue.model_action)}</span>
                    </div>
                  ) : issue.triage_verdict ? (
                    <div className="issue-card-meta">
                      <span className={`issue-triage-badge ${issue.triage_verdict}`} title={issue.triage_reason ?? ""}>
                        {issue.triage_verdict === "dismiss" ? "AI: Likely OK" : issue.triage_verdict === "keep" ? "AI: Review" : "AI: Unclear"}
                      </span>
                    </div>
                  ) : null}

                  <div className="issue-card-text">
                    <span className="issue-card-field">
                      <strong>Expected:</strong> {renderHighlightedText(issue.expected_text, normalizedSearch)}
                    </span>
                    <span className="issue-card-field">
                      <strong>Spoken:</strong> {renderHighlightedText(issue.spoken_text, normalizedSearch)}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
          {canScrollRight ? (
            <button type="button" className="issue-scroll-btn issue-scroll-right" onClick={() => scrollBy(1)} aria-label="Scroll right">
              &rsaquo;
            </button>
          ) : null}
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
