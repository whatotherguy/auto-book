import { useEffect, useRef, useMemo } from "react"

type SpokenToken = {
  index: number
  text: string
  normalized: string
  start_ms: number
  end_ms: number
  confidence: number
}

export function FollowAlongPanel({
  spokenTokens,
  manuscriptText,
  playbackTimeMs,
  isPlaying,
}: {
  spokenTokens: SpokenToken[]
  manuscriptText: string
  playbackTimeMs: number
  isPlaying: boolean
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLSpanElement>(null)

  // Find the current spoken token index based on playback time
  const activeTokenIndex = useMemo(() => {
    if (!spokenTokens.length || playbackTimeMs <= 0) return -1

    // Binary search for the token whose time range contains the playhead
    let lo = 0
    let hi = spokenTokens.length - 1
    let best = -1

    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      const token = spokenTokens[mid]
      if (playbackTimeMs >= token.start_ms && playbackTimeMs <= token.end_ms) {
        return mid
      }
      if (playbackTimeMs < token.start_ms) {
        hi = mid - 1
      } else {
        best = mid // playback is past this token
        lo = mid + 1
      }
    }

    return best
  }, [spokenTokens, playbackTimeMs])

  // Auto-scroll the active word into view
  useEffect(() => {
    if (activeRef.current && scrollRef.current) {
      activeRef.current.scrollIntoView({
        behavior: isPlaying ? "smooth" : "auto",
        block: "center",
        inline: "center",
      })
    }
  }, [activeTokenIndex, isPlaying])

  if (!spokenTokens.length) {
    return (
      <div className="follow-along">
        <div className="follow-along-empty muted">
          Run analysis to enable manuscript follow-along during playback.
        </div>
      </div>
    )
  }

  return (
    <div className="follow-along">
      <div className="follow-along-label">
        <span className="eyebrow">Manuscript Follow-Along</span>
      </div>
      <div className="follow-along-scroll" ref={scrollRef}>
        <div className="follow-along-text">
          {spokenTokens.map((token, index) => {
            const isActive = index === activeTokenIndex
            const isPast = index < activeTokenIndex
            const confidence = token.confidence

            return (
              <span
                key={index}
                ref={isActive ? activeRef : undefined}
                className={[
                  "follow-along-word",
                  isActive ? "active" : "",
                  isPast ? "past" : "",
                  confidence < 0.5 ? "low-confidence" : "",
                ].filter(Boolean).join(" ")}
              >
                {token.text}{" "}
              </span>
            )
          })}
        </div>
      </div>
    </div>
  )
}
