import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  analyzeChapter,
  cancelJob,
  getAcxCheck,
  getAltTakeClusters,
  getAudioSignals,
  getHealth,
  getLatestAnalysisJob,
  getJob,
  getSettings,
  getVadSegments,
  downloadChapterExport,
  downloadEditedChapterAudio,
  getChapter,
  getChapterAudioUrl,
  getIssues,
  setPreferredTake,
  startAutoEditJob,
  runAcxCheck,
  updateIssue,
  uploadChapterAudioWithProgress,
  getSpokenTokens
} from "../api"
import { AcxPanel } from "../components/AcxPanel"
import { JobStatus } from "../components/JobStatus"
import { IssueDetail } from "../components/IssueDetail"
import { IssueList } from "../components/IssueList"
import { IssueTimeline } from "../components/IssueTimeline"
import { ManuscriptPanel } from "../components/ManuscriptPanel"
import { SettingsPanel } from "../components/SettingsPanel"
import { Tooltip } from "../components/Tooltip"
import { KeyboardShortcutOverlay } from "../components/KeyboardShortcutOverlay"
import { WaveformPanel } from "../components/WaveformPanel"
import { Breadcrumb } from "../components/Breadcrumb"
import { TriageProgress } from "../components/TriageProgress"
import { ConfirmModal } from "../components/ConfirmModal"
import { UndoToast, nextToastId } from "../components/UndoToast"
import type { UndoToastData } from "../components/UndoToast"
import { SkeletonTimeline } from "../components/Skeleton"
import { AltTakeCluster, AcxCheck, AnalysisJob, AppSettings, AudioSignalRecord, Chapter, GpuInfo, Issue, IssueStatus, TranscriptionMode, VadSegmentRecord } from "../types"
import { AltTakesPanel } from "../components/AltTakesPanel"
import { ConfidenceFilter, ISSUE_TYPE_META } from "../utils"
import { cachedFetch, cacheInvalidate } from "../cache"

const ONBOARDING_KEY = "ab:onboarding-shortcuts-dismissed"

export function ChapterReviewPage({
  chapterId,
  projectId,
  projectName,
  onBack,
  onBackToProjects,
}: {
  chapterId: number
  projectId?: number | null
  projectName?: string | null
  onBack: () => void
  onBackToProjects?: () => void
}) {
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [issues, setIssues] = useState<Issue[]>([])
  const [selectedIssueId, setSelectedIssueId] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState("all")
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isReplacingAudio, setIsReplacingAudio] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isExportingCsv, setIsExportingCsv] = useState(false)
  const [isExportingJson, setIsExportingJson] = useState(false)
  const [isAutoEditing, setIsAutoEditing] = useState(false)
  const [acxReport, setAcxReport] = useState<AcxCheck | null>(null)
  const [isRunningAcx, setIsRunningAcx] = useState(false)
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null)
  const [autoEditJob, setAutoEditJob] = useState<AnalysisJob | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [isBatchUpdating, setIsBatchUpdating] = useState(false)
  const [transcriptionMode, setTranscriptionMode] = useState<TranscriptionMode>("optimized")
  const [forceRetranscribe, setForceRetranscribe] = useState(false)
  const [gpuInfo, setGpuInfo] = useState<GpuInfo | null>(null)
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [enableLlmTriage, setEnableLlmTriage] = useState(true)
  const [spokenTokens, setSpokenTokens] = useState<any[]>([])
  const [playbackTimeMs, setPlaybackTimeMs] = useState(0)
  const [audioSignals, setAudioSignals] = useState<AudioSignalRecord[]>([])
  const [vadSegments, setVadSegments] = useState<VadSegmentRecord[]>([])
  const [altTakeClusters, setAltTakeClusters] = useState<AltTakeCluster[]>([])
  const [actionsOpen, setActionsOpen] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(() => !localStorage.getItem(ONBOARDING_KEY))
  const [undoToast, setUndoToast] = useState<UndoToastData | null>(null)

  // Confirm modal state
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean
    title: string
    message: string
    confirmLabel: string
    variant: "danger" | "default"
    onConfirm: () => void
  }>({ open: false, title: "", message: "", confirmLabel: "Confirm", variant: "default", onConfirm: () => {} })

  const replacementAudioInputRef = useRef<HTMLInputElement | null>(null)
  const autoEditDownloadTriggeredRef = useRef(false)
  const issuesRef = useRef(issues)
  const selectedIssueRef = useRef<Issue | null>(null)

  const selectedIssue = useMemo(
    () => issues.find((issue) => issue.id === selectedIssueId) ?? null,
    [issues, selectedIssueId]
  )

  useEffect(() => {
    void cachedFetch("health", getHealth, 60_000).then((h) => setGpuInfo(h.gpu)).catch(() => {})
    void cachedFetch("settings", getSettings, 60_000).then(setAppSettings).catch(() => {})
  }, [])
  useEffect(() => { issuesRef.current = issues }, [issues])
  useEffect(() => { selectedIssueRef.current = selectedIssue }, [selectedIssue])

  function showConfirm(opts: { title: string; message: string; confirmLabel: string; variant?: "danger" | "default"; onConfirm: () => void }) {
    setConfirmModal({ open: true, variant: "default", ...opts })
  }

  function closeConfirm() {
    setConfirmModal((prev) => ({ ...prev, open: false }))
  }

  async function loadChapter(options?: { showLoading?: boolean }) {
    const showLoading = options?.showLoading ?? true

    try {
      if (showLoading) {
        setLoading(true)
      }
      setError(null)

      const [nextChapter, nextIssues, nextAcxReport, nextAnalysisJob, nextAutoEditJob] = await Promise.all([
        getChapter(chapterId),
        getIssues(chapterId),
        getAcxCheck(chapterId).catch(() => null),
        getLatestAnalysisJob(chapterId, "analyze_chapter").catch(() => null),
        getLatestAnalysisJob(chapterId, "export_edited_wav").catch(() => null)
      ])
      // After the main Promise.all, fetch spoken tokens and signal data
      getSpokenTokens(chapterId).then(setSpokenTokens).catch(() => setSpokenTokens([]))
      getAudioSignals(chapterId).then(setAudioSignals).catch(() => setAudioSignals([]))
      getVadSegments(chapterId).then(setVadSegments).catch(() => setVadSegments([]))
      getAltTakeClusters(chapterId).then(setAltTakeClusters).catch(() => setAltTakeClusters([]))

      setChapter(nextChapter)
      setTranscriptionMode((currentMode) => {
        const nextMode = nextChapter.transcription_mode
        if (nextMode === "optimized" || nextMode === "high_quality" || nextMode === "max_quality") {
          return nextMode
        }
        return nextChapter.analysis_artifact_updated_at ? currentMode : "optimized"
      })
      setIssues(nextIssues)
      setAcxReport(nextAcxReport)
      setAnalysisJob(nextAnalysisJob)
      setAutoEditJob(nextAutoEditJob)
      setSelectedIssueId((current) => {
        if (current != null && nextIssues.some((issue) => issue.id === current)) {
          return current
        }

        return nextIssues[0]?.id ?? null
      })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load chapter review data.")
    } finally {
      if (showLoading) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    void loadChapter()
  }, [chapterId])

  useEffect(() => {
    if (!analysisJob || (analysisJob.status !== "queued" && analysisJob.status !== "running")) {
      return
    }

    let active = true

    async function refreshAnalysisJob() {
      try {
        const nextJob = await getJob(analysisJob!.id)
        if (!active) {
          return
        }

        setAnalysisJob(nextJob)
        if (nextJob.status === "completed") {
          cacheInvalidate(`chapter:${chapterId}`)
          void loadChapter({ showLoading: false })
        }
      } catch {
        // Keep the last visible job state if polling briefly fails.
      }
    }

    void refreshAnalysisJob()
    const intervalId = window.setInterval(() => {
      void refreshAnalysisJob()
    }, 1500)

    return () => {
      active = false
      window.clearInterval(intervalId)
    }
  }, [analysisJob?.id, analysisJob?.status])

  useEffect(() => {
    if (!autoEditJob || (autoEditJob.status !== "queued" && autoEditJob.status !== "running")) {
      return
    }

    let active = true

    async function refreshAutoEditJob() {
      try {
        const nextJob = await getJob(autoEditJob!.id)
        if (!active) {
          return
        }

        setAutoEditJob(nextJob)
        if (nextJob.status === "completed" && !autoEditDownloadTriggeredRef.current) {
          autoEditDownloadTriggeredRef.current = true
          try {
            await downloadEditedChapterAudio(chapterId)
          } catch {
            autoEditDownloadTriggeredRef.current = false
            return
          }
          void loadChapter({ showLoading: false })
        }
      } catch {
        // Keep the last visible job state if polling briefly fails.
      }
    }

    void refreshAutoEditJob()
    const intervalId = window.setInterval(() => {
      void refreshAutoEditJob()
    }, 1500)

    return () => {
      active = false
      window.clearInterval(intervalId)
    }
  }, [autoEditJob?.id, autoEditJob?.status, chapterId])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return

      const currentIssues = issuesRef.current
      const currentSelectedIssue = selectedIssueRef.current

      if (event.key === "j" || event.key === "J") {
        event.preventDefault()
        setSelectedIssueId((current) => {
          const currentIndex = currentIssues.findIndex((i) => i.id === current)
          const nextIndex = currentIndex < currentIssues.length - 1 ? currentIndex + 1 : 0
          return currentIssues[nextIndex]?.id ?? current
        })
      }
      if (event.key === "k" || event.key === "K") {
        event.preventDefault()
        setSelectedIssueId((current) => {
          const currentIndex = currentIssues.findIndex((i) => i.id === current)
          const prevIndex = currentIndex > 0 ? currentIndex - 1 : currentIssues.length - 1
          return currentIssues[prevIndex]?.id ?? current
        })
      }
      if (event.key === "a" && !event.ctrlKey && !event.metaKey) {
        if (currentSelectedIssue) void handleIssueStatusChange(currentSelectedIssue, "approved").catch(() => {})
      }
      if (event.key === "r" && !event.ctrlKey && !event.metaKey) {
        if (currentSelectedIssue) void handleIssueStatusChange(currentSelectedIssue, "rejected").catch(() => {})
      }
      if (event.key === " ") {
        event.preventDefault()
        // Dispatch a custom event that WaveformPanel can listen to
        window.dispatchEvent(new CustomEvent("waveform-toggle-play"))
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [])

  const issueTypeOptions = useMemo(() => Object.entries(ISSUE_TYPE_META), [])

  const issueTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const issue of issues) {
      counts[issue.type] = (counts[issue.type] ?? 0) + 1
    }
    return counts
  }, [issues])

  function triggerReplacementUpload() {
    replacementAudioInputRef.current?.click()
  }

  async function handleReplacementAudioChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ""

    if (!file) {
      return
    }

    try {
      setIsReplacingAudio(true)
      setUploadProgress(0)
      setError(null)
      await uploadChapterAudioWithProgress(chapterId, file, setUploadProgress)
      cacheInvalidate(`chapter:${chapterId}`)
      await loadChapter({ showLoading: false })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to replace chapter WAV.")
    } finally {
      setIsReplacingAudio(false)
      setUploadProgress(null)
    }
  }

  async function handleAnalyzeChapter() {
    try {
      setIsAnalyzing(true)
      setError(null)
      const nextJob = await analyzeChapter(chapterId, transcriptionMode, forceRetranscribe, enableLlmTriage)
      setAnalysisJob({ id: nextJob.job_id, chapter_id: chapterId, type: "analyze_chapter", status: nextJob.status, progress: 0 })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to analyze chapter.")
    } finally {
      setIsAnalyzing(false)
    }
  }

  async function handleCancelJob(job: AnalysisJob | null, setJob: (j: AnalysisJob | null) => void) {
    if (!job || (job.status !== "queued" && job.status !== "running")) return
    try {
      setError(null)
      await cancelJob(job.id)
      setJob({ ...job, status: "failed", error_message: "Cancelled by user" })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to cancel job.")
    }
  }

  async function handleExport(kind: "csv" | "json") {
    try {
      setError(null)
      if (kind === "csv") {
        setIsExportingCsv(true)
      } else {
        setIsExportingJson(true)
      }
      await downloadChapterExport(chapterId, kind)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : `Failed to export ${kind.toUpperCase()}.`)
    } finally {
      if (kind === "csv") {
        setIsExportingCsv(false)
      } else {
        setIsExportingJson(false)
      }
    }
  }

  async function handleAutoEdit() {
    try {
      setIsAutoEditing(true)
      autoEditDownloadTriggeredRef.current = false
      setError(null)
      const nextJob = await startAutoEditJob(chapterId)
      setAutoEditJob({
        id: nextJob.job_id,
        chapter_id: chapterId,
        type: "export_edited_wav",
        status: nextJob.status,
        progress: 0
      })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to export auto-edited WAV.")
    } finally {
      setIsAutoEditing(false)
    }
  }

  async function handleRunAcxCheck() {
    try {
      setIsRunningAcx(true)
      setError(null)
      const nextReport = await runAcxCheck(chapterId)
      setAcxReport(nextReport)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to run ACX check.")
    } finally {
      setIsRunningAcx(false)
    }
  }

  async function handleBatchStatusChange(status: IssueStatus, filter?: { type?: string; confidence?: ConfidenceFilter; search?: string }) {
    const normalizedSearch = (filter?.search ?? "").trim().toLowerCase()
    const targetIssues = issues.filter((issue) => {
      if (issue.status === status) return false
      if (filter?.type && filter.type !== "all" && issue.type !== filter.type) return false
      if (filter?.confidence && filter.confidence !== "all") {
        if (filter.confidence === "high" && issue.confidence < 0.85) return false
        if (filter.confidence === "medium" && (issue.confidence < 0.65 || issue.confidence >= 0.85)) return false
        if (filter.confidence === "low" && issue.confidence >= 0.65) return false
      }
      if (normalizedSearch && ![issue.spoken_text, issue.expected_text, issue.context_before, issue.context_after].some((v) => v.toLowerCase().includes(normalizedSearch))) return false
      return true
    })
    if (targetIssues.length === 0) return

    const actionLabel = status === "approved" ? "Approve" : status === "rejected" ? "Reject" : "Mark for review"

    showConfirm({
      title: `${actionLabel} ${targetIssues.length} issues?`,
      message: `This will ${actionLabel.toLowerCase()} all ${targetIssues.length} issues matching the current filters.`,
      confirmLabel: actionLabel,
      variant: status === "rejected" ? "danger" : "default",
      onConfirm: async () => {
        closeConfirm()
        try {
          setIsBatchUpdating(true)
          setError(null)
          const updated = await Promise.all(targetIssues.map((issue) => updateIssue(issue.id, { status })))
          setIssues((current) => {
            const updatedMap = new Map(updated.map((u) => [u.id, u]))
            return current.map((issue) => updatedMap.get(issue.id) ?? issue)
          })
        } catch (nextError) {
          setError(nextError instanceof Error ? nextError.message : "Failed to batch update issues.")
        } finally {
          setIsBatchUpdating(false)
        }
      },
    })
  }

  const handleIssueStatusChange = useCallback(async function handleIssueStatusChange(issue: Issue, status: IssueStatus) {
    const previousStatus = issue.status
    try {
      setError(null)
      const updatedIssue = await updateIssue(issue.id, { status })
      setIssues((currentIssues) =>
        currentIssues.map((currentIssue) => (currentIssue.id === updatedIssue.id ? updatedIssue : currentIssue))
      )
      setSelectedIssueId(updatedIssue.id)

      // Show undo toast
      const label = status === "approved" ? "Approved" : status === "rejected" ? "Rejected" : "Marked for review"
      setUndoToast({
        id: nextToastId(),
        message: `${label} issue #${issue.id}`,
        onUndo: async () => {
          try {
            const reverted = await updateIssue(issue.id, { status: previousStatus })
            setIssues((currentIssues) =>
              currentIssues.map((ci) => (ci.id === reverted.id ? reverted : ci))
            )
          } catch {
            // Best effort
          }
        },
      })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to update issue.")
    }
  }, [])

  function handleNoteUpdated(updated: Issue) {
    setIssues((currentIssues) =>
      currentIssues.map((ci) => (ci.id === updated.id ? updated : ci))
    )
  }

  function dismissOnboarding() {
    setShowOnboarding(false)
    localStorage.setItem(ONBOARDING_KEY, "1")
  }

  const canAnalyze = Boolean(chapter?.has_audio && chapter?.raw_text?.trim())
  const hasAudio = Boolean(chapter?.has_audio || chapter?.audio_file_path)
  const isAnalysisRunning = isAnalyzing || analysisJob?.status === "queued" || analysisJob?.status === "running"
  const isAutoEditRunning = isAutoEditing || autoEditJob?.status === "queued" || autoEditJob?.status === "running"

  // Breadcrumb items
  const breadcrumbItems = useMemo(() => {
    const items: { label: string; onClick?: () => void }[] = [
      { label: "Projects", onClick: onBackToProjects },
    ]
    if (projectName || projectId) {
      items.push({ label: projectName ?? `Project ${projectId}`, onClick: onBack })
    }
    items.push({
      label: chapter?.title
        ? `Chapter ${chapter.chapter_number}: ${chapter.title}`
        : `Chapter ${chapter?.chapter_number ?? chapterId}`,
    })
    return items
  }, [projectName, projectId, chapter, chapterId, onBack, onBackToProjects])

  return (
    <div className="page app-shell review-page">
      <Breadcrumb items={breadcrumbItems} />

      <div className="page-hero review-hero">
        <p className="eyebrow">Chapter Review</p>
        <h1>{chapter?.title ? `Chapter ${chapter.chapter_number}: ${chapter.title}` : `Chapter ${chapter?.chapter_number ?? chapterId}`}</h1>
        <p className="hero-copy">
          Search issues by transcript context, inspect the waveform, and review suggested cut ranges without touching the source WAV.
        </p>
        {chapter?.transcription_model ? (
          <p className="muted">
            Last transcript: {chapter.transcription_mode ?? "optimized"} mode, {chapter.transcription_model} model
            {chapter.transcription_profile ? ` (${chapter.transcription_profile} profile)` : ""}
          </p>
        ) : null}
        {loading ? <p className="muted">Loading chapter data...</p> : null}
      </div>

      {error ? (
        <div className="card error" role="alert">
          {error}
        </div>
      ) : null}

      {/* Onboarding hint */}
      {showOnboarding && !loading && issues.length > 0 ? (
        <div className="onboarding-hint">
          <span>
            Navigate issues with <kbd>J</kbd> / <kbd>K</kbd>, approve with <kbd>A</kbd>, reject with <kbd>R</kbd>, play/pause with <kbd>Space</kbd>
          </span>
          <button type="button" className="onboarding-hint-dismiss" onClick={dismissOnboarding}>
            Dismiss
          </button>
        </div>
      ) : null}

      {/* Triage progress */}
      <TriageProgress issues={issues} />

      <div className="card review-toolbar">
        <div className="review-filter-bar">
          <div className="review-toolbar-fields">
            <label htmlFor="issue-search">
              Search
              <Tooltip text="Filter the issue list by spoken text, expected manuscript text, or surrounding context."><span className="muted"> (?)</span></Tooltip>
            </label>
            <input
              id="issue-search"
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search issues..."
            />
          </div>

          <div className="review-toolbar-fields">
            <label htmlFor="issue-type-filter">
              Type
              <Tooltip text="Filter by detection category."><span className="muted"> (?)</span></Tooltip>
            </label>
            <select id="issue-type-filter" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="all">All types ({issues.length})</option>
              {issueTypeOptions.map(([type, meta]) => (
                <option key={type} value={type}>
                  {meta.label} ({issueTypeCounts[type] ?? 0})
                </option>
              ))}
            </select>
          </div>

          <div className="review-toolbar-fields">
            <label htmlFor="confidence-filter">
              Confidence
              <Tooltip text="High (>=85%) = likely real. Low (<65%) = may be artifact."><span className="muted"> (?)</span></Tooltip>
            </label>
            <select id="confidence-filter" value={confidenceFilter} onChange={(event) => setConfidenceFilter(event.target.value as ConfidenceFilter)}>
              <option value="all">All levels</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div className="review-toolbar-fields">
            <label htmlFor="transcription-mode">
              Transcription
              <Tooltip text="Optimized is fastest. Max Quality uses the largest model."><span className="muted"> (?)</span></Tooltip>
            </label>
            <select id="transcription-mode" value={transcriptionMode} onChange={(event) => setTranscriptionMode(event.target.value as TranscriptionMode)} disabled={isAnalysisRunning}>
              <option value="optimized">Optimized{gpuInfo?.available ? " (GPU)" : ""}</option>
              <option value="high_quality">High Quality{gpuInfo?.available ? " (GPU)" : " (slow)"}</option>
              <option value="max_quality">Max Quality{gpuInfo?.available ? " (GPU)" : " (very slow)"}</option>
            </select>
            {gpuInfo ? (
              <span className="muted" style={{ fontSize: "0.72rem" }}>
                {gpuInfo.available ? `GPU: ${gpuInfo.name}` : "CPU only"}
              </span>
            ) : null}
          </div>
        </div>

        <div className="review-action-bar">
          <div className="action-group">
            <input ref={replacementAudioInputRef} type="file" accept=".wav,audio/wav" onChange={handleReplacementAudioChange} className="hidden-file-input" aria-label="Replace chapter WAV" />
            <button type="button" onClick={triggerReplacementUpload} disabled={isReplacingAudio}>
              {isReplacingAudio ? "Replacing..." : "Replace WAV"}
            </button>
            <button type="button" className="analyze-button" onClick={handleAnalyzeChapter} disabled={isAnalysisRunning || !canAnalyze}>
              {isAnalysisRunning ? <><span className="progress-ring" />Analyzing...</> : "Analyze"}
            </button>
            {isAnalysisRunning ? (
              <button type="button" className="danger-button" onClick={() => void handleCancelJob(analysisJob, setAnalysisJob)}>Cancel</button>
            ) : null}
          </div>

          <div className="action-group">
            <label className="toggle-row">
              <input type="checkbox" checked={forceRetranscribe} onChange={(e) => setForceRetranscribe(e.target.checked)} disabled={isAnalysisRunning} />
              <span>Re-transcribe</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={enableLlmTriage} onChange={(e) => setEnableLlmTriage(e.target.checked)} disabled={isAnalysisRunning || !appSettings?.triage_available} />
              <span>AI triage{!appSettings?.triage_available ? " (no key)" : ""}</span>
            </label>
          </div>

          <div className="action-group">
            <button
              type="button"
              className="toolbar-actions-toggle"
              onClick={() => setActionsOpen(!actionsOpen)}
            >
              {actionsOpen ? "Hide Actions" : "More Actions"}
            </button>
          </div>
        </div>

        <div className={`toolbar-actions-drawer ${actionsOpen ? "open" : ""}`}>
          <div className="action-group">
            <button type="button" onClick={() => void handleExport("csv")} disabled={isExportingCsv}>
              {isExportingCsv ? "CSV..." : "Export CSV"}
            </button>
            <button type="button" onClick={() => void handleExport("json")} disabled={isExportingJson}>
              {isExportingJson ? "JSON..." : "Export JSON"}
            </button>
            <button type="button" onClick={handleAutoEdit} disabled={isAutoEditRunning || !hasAudio}>
              {isAutoEditRunning ? <><span className="progress-ring" />Exporting...</> : "Auto Edit WAV"}
            </button>
            {isAutoEditRunning ? (
              <button type="button" className="danger-button" onClick={() => void handleCancelJob(autoEditJob, setAutoEditJob)}>Cancel</button>
            ) : null}
          </div>

          <div className="action-group">
            <button type="button" className="approve-button" onClick={() => void handleBatchStatusChange("approved", { type: typeFilter, confidence: confidenceFilter, search: searchQuery })} disabled={isBatchUpdating || issues.length === 0}>
              {isBatchUpdating ? "..." : "Approve Filtered"}
            </button>
            <button type="button" className="reject-button" onClick={() => void handleBatchStatusChange("rejected", { type: typeFilter, confidence: confidenceFilter, search: searchQuery })} disabled={isBatchUpdating || issues.length === 0}>
              Reject Filtered
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <SkeletonTimeline />
      ) : (
        <IssueTimeline
          issues={issues}
          selectedIssueId={selectedIssueId}
          durationMs={chapter?.duration_ms ?? 0}
          onSelect={(issue) => setSelectedIssueId(issue.id)}
          playheadMs={playbackTimeMs}
          audioSignals={audioSignals}
          vadSegments={vadSegments}
        />
      )}

      <WaveformPanel
        audioUrl={chapter ? getChapterAudioUrl(chapter.id, chapter.analysis_artifact_updated_at) : null}
        hasAudio={hasAudio}
        focusStartMs={selectedIssue?.start_ms}
        focusEndMs={selectedIssue?.end_ms}
        issueType={selectedIssue?.type}
        spokenTokens={spokenTokens}
        onTimeUpdate={setPlaybackTimeMs}
      />

      {/* Two-column review grid */}
      <div className="grid review-grid-2col">
        <div className="review-column">
          <IssueList
            issues={issues}
            selectedIssueId={selectedIssueId}
            onSelect={(issue) => setSelectedIssueId(issue.id)}
            searchQuery={searchQuery}
            typeFilter={typeFilter}
            confidenceFilter={confidenceFilter}
            loading={loading}
          />
        </div>

        <div className="review-column">
          <IssueDetail
            issue={selectedIssue}
            onStatusChange={handleIssueStatusChange}
            onNoteUpdated={handleNoteUpdated}
          />

          {altTakeClusters.length > 0 ? (
            <AltTakesPanel
              clusters={altTakeClusters}
              issues={issues}
              onSelectPreferred={async (clusterId, issueId) => {
                await setPreferredTake(clusterId, issueId)
                void loadChapter({ showLoading: false })
              }}
              onSelectIssue={(issue) => setSelectedIssueId(issue.id)}
            />
          ) : null}

          <ManuscriptPanel text={chapter?.raw_text ?? ""} />

          {uploadProgress != null || isReplacingAudio ? (
            <JobStatus
              title="WAV Upload"
              storageKey="chapter-review:wav-upload"
              status={isReplacingAudio ? "uploading" : "idle"}
              progress={uploadProgress ?? undefined}
              step={isReplacingAudio ? "replace_wav" : null}
            />
          ) : null}

          {analysisJob ? (
            <JobStatus
              status={analysisJob.status}
              progress={analysisJob.progress}
              step={analysisJob.current_step}
              errorMessage={analysisJob.error_message}
            />
          ) : null}

          {autoEditJob ? (
            <JobStatus
              title="Auto Edit Status"
              storageKey="chapter-review:auto-edit-status"
              status={autoEditJob.status}
              progress={autoEditJob.progress}
              step={autoEditJob.current_step}
              errorMessage={autoEditJob.error_message}
            />
          ) : null}

          <AcxPanel
            report={acxReport}
            onRun={handleRunAcxCheck}
            disabled={!hasAudio}
            isRunning={isRunningAcx}
          />

          <SettingsPanel settings={appSettings} onUpdate={setAppSettings} />
        </div>
      </div>

      <KeyboardShortcutOverlay />
      <UndoToast toast={undoToast} onDismiss={() => setUndoToast(null)} />
      <ConfirmModal
        open={confirmModal.open}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmLabel={confirmModal.confirmLabel}
        variant={confirmModal.variant}
        onConfirm={confirmModal.onConfirm}
        onCancel={closeConfirm}
      />
    </div>
  )
}
