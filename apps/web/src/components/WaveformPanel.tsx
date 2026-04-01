import { useEffect, useMemo, useRef, useState } from "react"
import WaveSurfer from "wavesurfer.js"
import { CollapsibleSection } from "./CollapsibleSection"

type SpokenToken = {
  index: number
  text: string
  normalized: string
  start_ms: number
  end_ms: number
  confidence: number
}

const PREVIEW_LEAD_MS = 1200
const PREVIEW_TAIL_MS = 1800

export function WaveformPanel({
  audioUrl,
  hasAudio,
  focusStartMs,
  focusEndMs,
  issueType,
  onTimeUpdate,
  onPlayStateChange,
  spokenTokens,
}: {
  audioUrl: string | null | undefined
  hasAudio: boolean
  focusStartMs?: number | null
  focusEndMs?: number | null
  issueType?: string | null
  onTimeUpdate?: (timeMs: number) => void
  onPlayStateChange?: (playing: boolean) => void
  spokenTokens?: SpokenToken[]
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const waveSurferRef = useRef<WaveSurfer | null>(null)
  const previewEndRef = useRef<number | null>(null)
  const focusStartRef = useRef<number | null>(focusStartMs ?? null)
  const focusEndRef = useRef<number | null>(focusEndMs ?? null)
  const simulateEditRef = useRef(false)
  const [simulateEdit, setSimulateEdit] = useState(false)
  const [playbackTime, setPlaybackTime] = useState(0)
  const [durationSeconds, setDurationSeconds] = useState(0)
  const [waveformError, setWaveformError] = useState<string | null>(null)
  const [waveSurferReady, setWaveSurferReady] = useState(false)
  const [waveformZoom, setWaveformZoom] = useState(1)
  const [playbackRate, setPlaybackRate] = useState(1)
  const onTimeUpdateRef = useRef(onTimeUpdate)
  const onPlayStateChangeRef = useRef(onPlayStateChange)
  useEffect(() => { onTimeUpdateRef.current = onTimeUpdate }, [onTimeUpdate])
  useEffect(() => { onPlayStateChangeRef.current = onPlayStateChange }, [onPlayStateChange])

  useEffect(() => {
    focusStartRef.current = focusStartMs ?? null
    focusEndRef.current = focusEndMs ?? null
  }, [focusStartMs, focusEndMs])

  useEffect(() => {
    simulateEditRef.current = simulateEdit
  }, [simulateEdit])

  useEffect(() => {
    if (!containerRef.current) return

    const ws = WaveSurfer.create({
      container: containerRef.current,
      height: 120,
      waveColor: "#66e3ff",
      progressColor: "#8b5cf6",
      cursorColor: "#f8fafc",
      barWidth: 2,
      barGap: 1,
      barRadius: 999
    })

    waveSurferRef.current = ws
    setWaveSurferReady(true)

    function handleWaveformError(error: unknown) {
      const message = error instanceof Error ? error.message : String(error)
      console.error("Waveform load error:", error)
      setWaveformError(message)
      setDurationSeconds(0)
      setPlaybackTime(0)
      previewEndRef.current = null
      ws.empty()
    }

    const unsubscribeReady = ws.on("ready", () => {
      setDurationSeconds(ws.getDuration())
    })
    const unsubscribeError = ws.on("error", handleWaveformError)
    const unsubscribeTimeupdate = ws.on("timeupdate", (currentTime) => {
      setPlaybackTime(currentTime)
      onTimeUpdateRef.current?.(Math.round(currentTime * 1000))

      if (previewEndRef.current != null && currentTime >= previewEndRef.current) {
        ws.pause()
        previewEndRef.current = null
        return
      }

      if (
        simulateEditRef.current &&
        focusStartRef.current != null &&
        focusEndRef.current != null &&
        currentTime >= focusStartRef.current / 1000 &&
        currentTime < focusEndRef.current / 1000
      ) {
        ws.setTime(focusEndRef.current / 1000)
      }
    })

    const unsubscribePlay = ws.on("play", () => onPlayStateChangeRef.current?.(true))
    const unsubscribePause = ws.on("pause", () => onPlayStateChangeRef.current?.(false))

    function handleTogglePlay() {
      ws.playPause()
    }
    window.addEventListener("waveform-toggle-play", handleTogglePlay)

    return () => {
      unsubscribeReady()
      unsubscribeError()
      unsubscribeTimeupdate()
      unsubscribePlay()
      unsubscribePause()
      window.removeEventListener("waveform-toggle-play", handleTogglePlay)
      ws.destroy()
    }
  }, [])

  useEffect(() => {
    const ws = waveSurferRef.current
    if (!ws || !waveSurferReady) return

    setWaveformError(null)

    if (!audioUrl) {
      setWaveformError("No audio file available")
      previewEndRef.current = null
      setDurationSeconds(0)
      setPlaybackTime(0)
      ws.empty()
      return
    }

    ws.empty()
    void ws.load(audioUrl).catch((error) => {
      setWaveformError(error instanceof Error ? error.message : String(error))
    })
  }, [audioUrl, waveSurferReady])

  useEffect(() => {
    const ws = waveSurferRef.current
    if (!ws || focusStartMs == null || durationSeconds <= 0) return

    previewEndRef.current = null
    ws.setTime(focusStartMs / 1000)
  }, [focusStartMs, durationSeconds])

  const issueStartSeconds = focusStartMs != null ? focusStartMs / 1000 : null
  const issueEndSeconds = focusEndMs != null ? focusEndMs / 1000 : null
  const previewStartSeconds =
    issueStartSeconds != null ? Math.max(issueStartSeconds - PREVIEW_LEAD_MS / 1000, 0) : null
  const previewEndSeconds =
    issueEndSeconds != null
      ? Math.min(
          issueEndSeconds + PREVIEW_TAIL_MS / 1000,
          durationSeconds > 0 ? durationSeconds : issueEndSeconds + PREVIEW_TAIL_MS / 1000
        )
      : null
  const skipSpanSeconds =
    issueStartSeconds != null && issueEndSeconds != null
      ? Math.max(issueEndSeconds - issueStartSeconds, 0)
      : 0

  function formatSeconds(value: number) {
    const totalSeconds = Math.max(0, Math.floor(value))
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    return `${minutes}:${seconds.toString().padStart(2, "0")}`
  }

  function formatWindow(startMs: number, endMs: number) {
    return `${formatSeconds(startMs / 1000)} to ${formatSeconds(endMs / 1000)}`
  }

  function handlePlayPause() {
    const ws = waveSurferRef.current
    if (!ws || waveformError) return

    if (!ws.isPlaying()) {
      previewEndRef.current = null
    }

    ws.playPause()
  }

  function handlePreviewPlayback() {
    const ws = waveSurferRef.current
    if (!ws || waveformError || previewStartSeconds == null || previewEndSeconds == null) return

    previewEndRef.current = previewEndSeconds
    ws.setTime(previewStartSeconds)
    void ws.play()
  }

  return (
    <CollapsibleSection title="Waveform" storageKey="chapter-review:waveform">
      <div className="waveform-stage">
        <div className="waveform" ref={containerRef} aria-live="polite" />
        {waveformError ? (
          <div className="waveform-error" role="alert">
            <strong>
              {waveformError === "No audio file available"
                ? waveformError
                : "Audio could not be loaded. The file may be corrupted or in an unsupported format."}
            </strong>
          </div>
        ) : null}
      </div>
      <div className="waveform-zoom">
        <label htmlFor="waveform-zoom">Gain</label>
        <input
          id="waveform-zoom"
          type="range"
          min={1}
          max={8}
          step={0.5}
          value={waveformZoom}
          onChange={(e) => {
            const zoom = parseFloat(e.target.value)
            setWaveformZoom(zoom)
            waveSurferRef.current?.setOptions({ height: Math.round(120 * zoom) })
          }}
        />
        <span className="muted">{waveformZoom}x</span>
      </div>
      <div className="playback-speed">
        <label htmlFor="playback-rate">Speed</label>
        <select
          id="playback-rate"
          value={playbackRate}
          onChange={(e) => {
            const rate = parseFloat(e.target.value)
            setPlaybackRate(rate)
            waveSurferRef.current?.setPlaybackRate(rate)
          }}
        >
          <option value={0.5}>0.5x</option>
          <option value={0.75}>0.75x</option>
          <option value={1}>1x</option>
          <option value={1.25}>1.25x</option>
          <option value={1.5}>1.5x</option>
          <option value={2}>2x</option>
        </select>
      </div>
      <FollowAlongStrip tokens={spokenTokens ?? []} playbackTimeMs={Math.round(playbackTime * 1000)} isPlaying={waveSurferRef.current?.isPlaying() ?? false} />
      {focusStartMs != null ? (
        <div className="waveform-controls">
          <div className="waveform-summary">
            <strong>Selected Review Window</strong>
            <p className="muted">
              {focusEndMs != null
                ? `${issueType ? issueType.replace(/_/g, " ") : "Issue"} at ${formatWindow(focusStartMs, focusEndMs)}`
                : `Issue starts at ${formatSeconds(focusStartMs / 1000)}`}
            </p>
          </div>
          <div className="row">
            <button onClick={() => waveSurferRef.current?.setTime(focusStartMs / 1000)}>Jump to Issue</button>
            <button onClick={handlePlayPause} disabled={!hasAudio}>
              Play or Pause
            </button>
            <button
              onClick={handlePreviewPlayback}
              disabled={!hasAudio || previewStartSeconds == null || previewEndSeconds == null}
            >
              Preview Edited Join
            </button>
          </div>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={simulateEdit}
              onChange={(event) => setSimulateEdit(event.target.checked)}
              disabled={!hasAudio || focusEndMs == null}
            />
            <span>
              Preview edit for this issue
              {issueType ? ` (${issueType.replace(/_/g, " ")})` : ""}
            </span>
          </label>
          <div className="waveform-meta">
            {focusEndMs != null ? (
              <span className="muted">Issue Window: {formatWindow(focusStartMs, focusEndMs)}</span>
            ) : null}
            {skipSpanSeconds > 0 ? (
              <span className="muted">Suggested Cut: {skipSpanSeconds.toFixed(2)}s</span>
            ) : null}
            {previewStartSeconds != null && previewEndSeconds != null ? (
              <span className="muted">
                Preview Span: {formatSeconds(previewStartSeconds)} to {formatSeconds(previewEndSeconds)}
              </span>
            ) : null}
            <span className="muted">Playhead: {formatSeconds(playbackTime)}</span>
          </div>
          <p className="muted">
            {simulateEdit
              ? "Playback will jump over the selected cut range so you can hear the stitched result."
              : "Toggle preview edit to hear the selected issue as if the cut were already applied."}
          </p>
        </div>
      ) : null}
      <p className="muted">
        {hasAudio
          ? "Loaded chapter WAV for review. Select an issue to jump directly into its timing window."
          : "Upload a WAV to populate the review waveform."}
      </p>
    </CollapsibleSection>
  )
}


function useThrottledValue<T>(value: T, intervalMs: number): T {
  const [throttled, setThrottled] = useState(value)
  const lastRef = useRef(0)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    const now = Date.now()
    if (now - lastRef.current >= intervalMs) {
      lastRef.current = now
      setThrottled(value)
    } else if (timerRef.current == null) {
      timerRef.current = window.setTimeout(() => {
        lastRef.current = Date.now()
        setThrottled(value)
        timerRef.current = null
      }, intervalMs - (now - lastRef.current))
    }
    return () => {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [value, intervalMs])

  return throttled
}

function FollowAlongStrip({ tokens, playbackTimeMs, isPlaying }: { tokens: SpokenToken[]; playbackTimeMs: number; isPlaying: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLSpanElement>(null)
  const throttledTimeMs = useThrottledValue(playbackTimeMs, 200) // ~5Hz

  const activeIndex = useMemo(() => {
    if (!tokens.length || throttledTimeMs <= 0) return -1
    let lo = 0
    let hi = tokens.length - 1
    let best = -1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      const t = tokens[mid]
      if (throttledTimeMs >= t.start_ms && throttledTimeMs <= t.end_ms) return mid
      if (throttledTimeMs < t.start_ms) { hi = mid - 1 } else { best = mid; lo = mid + 1 }
    }
    return best
  }, [tokens, throttledTimeMs])

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: isPlaying ? "smooth" : "auto", block: "nearest", inline: "center" })
    }
  }, [activeIndex, isPlaying])

  if (!tokens.length) return null

  return (
    <div className="follow-along-strip" ref={scrollRef}>
      {tokens.map((token, i) => (
        <span
          key={i}
          ref={i === activeIndex ? activeRef : undefined}
          className={`fa-word${i === activeIndex ? " active" : ""}${i < activeIndex ? " past" : ""}${token.confidence < 0.5 ? " low-conf" : ""}`}
        >
          {token.text}{" "}
        </span>
      ))}
    </div>
  )
}
