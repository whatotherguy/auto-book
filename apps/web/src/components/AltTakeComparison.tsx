import { useEffect, useRef, useState } from "react"
import { AltTakeCluster, Issue } from "../types"
import { formatTimecode } from "../utils"

type AltTakeComparisonProps = {
  cluster: AltTakeCluster
  issues: Issue[]
  audioUrl: string | null
  onSelectPreferred: (clusterId: number, issueId: number) => Promise<void>
  onClose: () => void
}

export function AltTakeComparison({
  cluster,
  issues,
  audioUrl,
  onSelectPreferred,
  onClose,
}: AltTakeComparisonProps) {
  const [playingId, setPlayingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const loadedUrlRef = useRef<string | null>(null)
  const listenersRef = useRef<{ timeupdate?: () => void; ended?: () => void }>({})

  const memberIssues = cluster.members
    .map((m) => issues.find((i) => i.id === m.issue_id))
    .filter((i): i is Issue => i != null)
    .sort((a, b) => a.start_ms - b.start_ms)

  const ranking = cluster.ranking

  useEffect(() => {
    return () => {
      const audio = audioRef.current
      if (audio) {
        audio.pause()
        if (listenersRef.current.timeupdate) audio.removeEventListener("timeupdate", listenersRef.current.timeupdate)
        if (listenersRef.current.ended) audio.removeEventListener("ended", listenersRef.current.ended)
        audio.src = ""
      }
    }
  }, [])

  function playTake(issue: Issue) {
    if (!audioUrl) return

    if (playingId === issue.id) {
      audioRef.current?.pause()
      setPlayingId(null)
      return
    }

    if (!audioRef.current) {
      audioRef.current = new Audio()
    }
    const audio = audioRef.current
    audio.pause()

    // Remove previous listeners using saved references
    if (listenersRef.current.timeupdate) audio.removeEventListener("timeupdate", listenersRef.current.timeupdate)
    if (listenersRef.current.ended) audio.removeEventListener("ended", listenersRef.current.ended)

    const startTime = issue.start_ms / 1000
    const endTime = issue.end_ms / 1000

    function onTimeUpdate() {
      if (audio.currentTime >= endTime) {
        audio.pause()
        setPlayingId(null)
      }
    }
    function onEnded() {
      setPlayingId(null)
    }

    listenersRef.current = { timeupdate: onTimeUpdate, ended: onEnded }
    audio.addEventListener("timeupdate", onTimeUpdate)
    audio.addEventListener("ended", onEnded)

    setPlayingId(issue.id)

    function startPlayback() {
      audio.currentTime = startTime
      void audio.play()
    }

    if (loadedUrlRef.current === audioUrl) {
      startPlayback()
    } else {
      audio.src = audioUrl
      loadedUrlRef.current = audioUrl
      audio.addEventListener("loadedmetadata", startPlayback, { once: true })
    }
  }

  async function handleSelect(issueId: number) {
    setSaving(true)
    try {
      await onSelectPreferred(cluster.id, issueId)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="alt-compare-overlay" onClick={onClose}>
      <div className="alt-compare-modal" onClick={(e) => e.stopPropagation()}>
        <div className="alt-compare-header">
          <div>
            <h3>Compare Alternate Takes</h3>
            <p className="muted">
              "{cluster.manuscript_text.slice(0, 80)}{cluster.manuscript_text.length > 80 ? "..." : ""}"
            </p>
          </div>
          <button type="button" className="job-popup-btn" onClick={onClose} aria-label="Close">&times;</button>
        </div>

        <div className="alt-compare-grid">
          {memberIssues.map((issue, idx) => {
            const isPreferred = cluster.preferred_issue_id === issue.id
            const isCurrentlyPlaying = playingId === issue.id
            const rankedTake = ranking?.ranked_takes?.find((t) => t.issue_id === issue.id)

            return (
              <div key={issue.id} className={`alt-compare-card${isPreferred ? " preferred" : ""}`}>
                <div className="alt-compare-card-header">
                  <span className="alt-compare-take-num">Take {idx + 1}</span>
                  {isPreferred ? <span className="alt-compare-preferred-badge">Preferred</span> : null}
                  {rankedTake ? <span className="muted">Rank #{rankedTake.rank}</span> : null}
                </div>

                <div className="alt-compare-time">
                  {formatTimecode(issue.start_ms)} - {formatTimecode(issue.end_ms)}
                </div>

                <div className="alt-compare-text">
                  <div className="alt-compare-field">
                    <strong>Spoken:</strong> {issue.spoken_text}
                  </div>
                  <div className="alt-compare-field">
                    <strong>Expected:</strong> {issue.expected_text}
                  </div>
                </div>

                {rankedTake ? (
                  <div className="alt-compare-scores">
                    <ScoreBar label="Quality" value={rankedTake.performance_quality} />
                    <ScoreBar label="Fit" value={rankedTake.continuity_fit} />
                    <ScoreBar label="Text" value={rankedTake.text_accuracy} />
                    <ScoreBar label="Splice" value={rankedTake.splice_readiness} />
                    <div className="alt-compare-total">
                      Total: <strong>{rankedTake.total_score.toFixed(2)}</strong>
                    </div>
                  </div>
                ) : null}

                {issue.prosody_features ? (
                  <div className="alt-compare-prosody">
                    {issue.prosody_features.speech_rate_wps.toFixed(1)} wps
                    {issue.prosody_features.f0_mean_hz != null
                      ? ` \u00b7 ${Math.round(issue.prosody_features.f0_mean_hz)} Hz`
                      : ""}
                  </div>
                ) : null}

                <div className="alt-compare-actions">
                  <button
                    type="button"
                    className={`alt-compare-play-btn${isCurrentlyPlaying ? " playing" : ""}`}
                    onClick={() => playTake(issue)}
                    disabled={!audioUrl}
                  >
                    {isCurrentlyPlaying ? "\u23F8 Pause" : "\u25B6 Listen"}
                  </button>
                  {!isPreferred ? (
                    <button
                      type="button"
                      className="alt-compare-select-btn"
                      disabled={saving}
                      onClick={() => void handleSelect(issue.id)}
                    >
                      {saving ? "..." : "Select This Take"}
                    </button>
                  ) : (
                    <span className="alt-compare-selected-label">Selected</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {ranking?.selection_reasons?.length ? (
          <div className="alt-compare-footer">
            <strong>AI Recommendation:</strong> {ranking.selection_reasons.join(". ")}
            {ranking.confidence < 0.6 ? " (close call)" : ""}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(Math.max(value * 100, 0), 100)
  return (
    <div className="alt-compare-score-row">
      <span className="alt-compare-score-label">{label}</span>
      <div className="alt-compare-score-bar">
        <div className="alt-compare-score-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="alt-compare-score-value">{value.toFixed(2)}</span>
    </div>
  )
}
