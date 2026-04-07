import { useEffect, useRef, useState } from "react"
import { AltTakeCluster, AltTakeMember, Issue } from "../types"
import { formatTimecode, humanize } from "../utils"

type AltTakeComparisonProps = {
  cluster: AltTakeCluster
  issues: Issue[]
  audioUrl: string | null
  onSelectPreferred: (clusterId: number, issueId: number) => Promise<void>
  onRejectTake: (issue: Issue) => Promise<void>
  onClose: () => void
}

export function AltTakeComparison({
  cluster,
  issues,
  audioUrl,
  onSelectPreferred,
  onRejectTake,
  onClose,
}: AltTakeComparisonProps) {
  const [playingId, setPlayingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const loadedUrlRef = useRef<string | null>(null)
  const rafRef = useRef<number | null>(null)
  const endTimeRef = useRef<number>(0)

  const memberIssues = cluster.members
    .map((m) => {
      const issue = issues.find((i) => i.id === m.issue_id)
      return issue ? { issue, takeOrder: m.take_order, member: m } : null
    })
    .filter((entry): entry is { issue: Issue; takeOrder: number; member: AltTakeMember } => entry != null)
    .sort((a, b) => a.takeOrder - b.takeOrder)

  const ranking = cluster.ranking

  function stopPlayback() {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    audioRef.current?.pause()
    setPlayingId(null)
  }

  function startRafLoop(audio: HTMLAudioElement) {
    function tick() {
      if (audio.paused || audio.ended) {
        setPlayingId(null)
        rafRef.current = null
        return
      }
      if (audio.currentTime >= endTimeRef.current) {
        audio.pause()
        setPlayingId(null)
        rafRef.current = null
        return
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }

  useEffect(() => {
    function handleWaveformPlaying() {
      stopPlayback()
    }
    window.addEventListener("waveform-playing", handleWaveformPlaying)
    return () => {
      window.removeEventListener("waveform-playing", handleWaveformPlaying)
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
      const audio = audioRef.current
      if (audio) {
        audio.pause()
        audio.src = ""
      }
    }
  }, [])

  function playTake(issue: Issue, member: AltTakeMember) {
    if (!audioUrl) return

    if (playingId === issue.id) {
      stopPlayback()
      return
    }

    // Stop any current playback
    stopPlayback()

    if (!audioRef.current) {
      audioRef.current = new Audio()
    }
    const audio = audioRef.current

    // Use playback bounds from member if available, otherwise fall back to issue bounds.
    // Playback bounds may be absent for clusters created before this feature was added,
    // or if the backend playback window computation failed for some reason.
    const playbackStart = member.playback_start_ms ?? issue.start_ms
    const playbackEnd = member.playback_end_ms ?? issue.end_ms

    const startTime = playbackStart / 1000
    endTimeRef.current = playbackEnd / 1000

    setPlayingId(issue.id)
    window.dispatchEvent(new CustomEvent("alt-take-playing"))

    function beginPlay() {
      audio.currentTime = startTime
      const playPromise = audio.play()
      if (playPromise) {
        playPromise.then(() => startRafLoop(audio)).catch(() => setPlayingId(null))
      }
    }

    if (loadedUrlRef.current === audioUrl) {
      beginPlay()
    } else {
      audio.src = audioUrl
      loadedUrlRef.current = audioUrl
      audio.addEventListener("loadedmetadata", beginPlay, { once: true })
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

        <div className="alt-compare-manuscript">
          <strong>Manuscript:</strong> "{cluster.manuscript_text}"
        </div>

        <div className="alt-compare-grid">
          {memberIssues.map(({ issue, takeOrder, member }) => {
            const isPreferred = cluster.preferred_issue_id === issue.id
            const isCurrentlyPlaying = playingId === issue.id
            const rankedTake = ranking?.ranked_takes?.find((t) => t.issue_id === issue.id)
            const isRejected = issue.status === "rejected"
            const spokenMatchesExpected = issue.spoken_text.trim().toLowerCase() === issue.expected_text.trim().toLowerCase()

            if (isRejected) return null

            return (
              <div key={issue.id} className={`alt-compare-card${isPreferred ? " preferred" : ""}`}>
                <div className="alt-compare-card-header">
                  <span className="alt-compare-take-num">Take {takeOrder + 1}</span>
                  {isPreferred ? <span className="alt-compare-preferred-badge">Preferred</span> : null}
                  {rankedTake ? <span className="muted">Rank #{rankedTake.rank}</span> : null}
                </div>

                {member.base_issue_type ? (
                  <div className="alt-compare-trigger muted" style={{ fontSize: "0.82em", marginBottom: 4 }}>
                    Original trigger: <strong>{humanize(member.base_issue_type)}</strong>
                  </div>
                ) : null}

                <div className="alt-compare-spoken-text">
                  "{issue.spoken_text}"
                  {!spokenMatchesExpected && (
                    <span className="alt-compare-text-mismatch" title="Spoken text differs from manuscript">
                      (differs from manuscript)
                    </span>
                  )}
                </div>

                <div className="alt-compare-time muted">
                  {formatTimecode(issue.start_ms)} - {formatTimecode(issue.end_ms)}
                </div>

                {rankedTake ? (
                  <div className="alt-compare-scores">
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
                    onClick={() => playTake(issue, member)}
                    disabled={!audioUrl}
                  >
                    {isCurrentlyPlaying ? "\u23F8 Pause" : "\u25B6 Listen"}
                  </button>
                  {!isPreferred ? (
                    <>
                      <button
                        type="button"
                        className="alt-compare-select-btn"
                        disabled={saving}
                        onClick={() => void handleSelect(issue.id)}
                      >
                        {saving ? "..." : "Select This Take"}
                      </button>
                      <button
                        type="button"
                        className="alt-compare-reject-btn"
                        disabled={saving}
                        onClick={() => void onRejectTake(issue)}
                        title="Mark for cut and remove from comparison"
                      >
                        Cut
                      </button>
                    </>
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
