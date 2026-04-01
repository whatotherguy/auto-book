import { useEffect, useMemo, useRef } from "react"
import { CollapsibleSection } from "./CollapsibleSection"

export function ManuscriptPanel({
  text,
  highlightText,
}: {
  text: string
  highlightText?: string | null
}) {
  const highlightRef = useRef<HTMLSpanElement>(null)

  // Find the best match position in the manuscript for the issue's expected text
  const segments = useMemo(() => {
    if (!text || !highlightText) return null

    const needle = highlightText.trim().toLowerCase()
    if (needle.length < 3) return null

    const idx = text.toLowerCase().indexOf(needle)
    if (idx === -1) return null

    return {
      before: text.slice(0, idx),
      match: text.slice(idx, idx + highlightText.trim().length),
      after: text.slice(idx + highlightText.trim().length),
    }
  }, [text, highlightText])

  // Auto-scroll to highlighted text when it changes
  useEffect(() => {
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" })
    }
  }, [segments])

  return (
    <CollapsibleSection
      title="Manuscript"
      className="manuscript"
      defaultCollapsed={false}
      storageKey="chapter-review:manuscript"
    >
      {segments ? (
        <pre>
          {segments.before}
          <span ref={highlightRef} className="manuscript-highlight">{segments.match}</span>
          {segments.after}
        </pre>
      ) : (
        <pre>{text || "No manuscript text loaded."}</pre>
      )}
    </CollapsibleSection>
  )
}
