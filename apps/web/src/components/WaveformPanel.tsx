import { useEffect, useRef, useState } from "react"
import WaveSurfer from "wavesurfer.js"
import { CollapsibleSection } from "./CollapsibleSection"

const PREVIEW_LEAD_MS = 1200
const PREVIEW_TAIL_MS = 1800

export function WaveformPanel({
  audioUrl,
  hasAudio,
  focusStartMs,
  focusEndMs,
  issueType
}: {
  audioUrl: string | null | undefined
  hasAudio: boolean
  focusStartMs?: number | null
  focusEndMs?: number | null
  issueType?: string | null
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

    return () => {
      unsubscribeReady()
      unsubscribeError()
      unsubscribeTimeupdate()
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

    void ws.load(audioUrl).catch((error) => {
      setWaveformError(error instanceof Error ? error.message : String(error))
    })
  }, [audioUrl, waveSurferReady])

  useEffect(() => {
    const ws = waveSurferRef.current
    if (!ws || focusStartMs == null) return

    previewEndRef.current = null
    ws.setTime(focusStartMs / 1000)
  }, [focusStartMs])

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
    ws.play()
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
      {focusStartMs != null ? (
        <div className="waveform-controls">
          <div className="waveform-summary">
            <strong>Selected Review Window</strong>
            <p className="muted">
              {focusEndMs != null
                ? `${issueType ? issueType.replaceAll("_", " ") : "Issue"} at ${formatWindow(focusStartMs, focusEndMs)}`
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
              {issueType ? ` (${issueType.replaceAll("_", " ")})` : ""}
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
