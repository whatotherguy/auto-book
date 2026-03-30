import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react"
import {
  analyzeChapter,
  getAcxCheck,
  getLatestAnalysisJob,
  getJob,
  downloadChapterExport,
  downloadEditedChapterAudio,
  getChapter,
  getChapterAudioUrl,
  getIssues,
  startAutoEditJob,
  runAcxCheck,
  updateIssue,
  uploadChapterAudioWithProgress
} from "../api"
import { AcxPanel } from "../components/AcxPanel"
import { JobStatus } from "../components/JobStatus"
import { IssueDetail } from "../components/IssueDetail"
import { IssueList } from "../components/IssueList"
import { IssueTimeline } from "../components/IssueTimeline"
import { ManuscriptPanel } from "../components/ManuscriptPanel"
import { WaveformPanel } from "../components/WaveformPanel"
import { AcxCheck, AnalysisJob, Chapter, Issue, TranscriptionMode } from "../types"
import { ConfidenceFilter, ISSUE_TYPE_META } from "../utils"

export function ChapterReviewPage({
  chapterId,
  onBack
}: {
  chapterId: number
  onBack: () => void
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
  const [transcriptionMode, setTranscriptionMode] = useState<TranscriptionMode>("optimized")
  const replacementAudioInputRef = useRef<HTMLInputElement | null>(null)
  const autoEditDownloadTriggeredRef = useRef(false)

  const selectedIssue = useMemo(
    () => issues.find((issue) => issue.id === selectedIssueId) ?? null,
    [issues, selectedIssueId]
  )

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
        const nextJob = await getJob(analysisJob.id)
        if (!active) {
          return
        }

        setAnalysisJob(nextJob)
        if (nextJob.status === "completed") {
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
        const nextJob = await getJob(autoEditJob.id)
        if (!active) {
          return
        }

        setAutoEditJob(nextJob)
        if (nextJob.status === "completed" && !autoEditDownloadTriggeredRef.current) {
          autoEditDownloadTriggeredRef.current = true
          await downloadEditedChapterAudio(chapterId)
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

  const issueTypeOptions = useMemo(() => Object.entries(ISSUE_TYPE_META), [])

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
      const nextJob = await analyzeChapter(chapterId, transcriptionMode)
      setAnalysisJob({ id: nextJob.job_id, chapter_id: chapterId, type: "analyze_chapter", status: nextJob.status, progress: 0 })
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to analyze chapter.")
    } finally {
      setIsAnalyzing(false)
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
      setIsExportingCsv(false)
      setIsExportingJson(false)
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

  async function handleIssueStatusChange(issue: Issue, status: string) {
    try {
      setError(null)
      const updatedIssue = await updateIssue(issue.id, { status })
      setIssues((currentIssues) =>
        currentIssues.map((currentIssue) => (currentIssue.id === updatedIssue.id ? updatedIssue : currentIssue))
      )
      setSelectedIssueId(updatedIssue.id)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to update issue.")
      throw nextError
    }
  }

  const canAnalyze = Boolean(chapter?.has_audio && chapter?.raw_text?.trim())
  const hasAudio = Boolean(chapter?.has_audio || chapter?.audio_file_path)
  const isAnalysisRunning = isAnalyzing || analysisJob?.status === "queued" || analysisJob?.status === "running"
  const isAutoEditRunning = isAutoEditing || autoEditJob?.status === "queued" || autoEditJob?.status === "running"

  return (
    <div className="page app-shell review-page">
      <button type="button" onClick={onBack}>
        Back to Project
      </button>

      <div className="page-hero review-hero">
        <p className="eyebrow">Chapter Review</p>
        <h1>{chapter?.title ? `Chapter ${chapter.chapter_number}: ${chapter.title}` : `Chapter ${chapter?.chapter_number ?? chapterId}`}</h1>
        <p className="hero-copy">
          Search issues by transcript context, inspect the waveform, and review suggested cut ranges without touching the source WAV.
        </p>
        {chapter?.transcription_model ? (
          <p className="muted">
            Last transcript used {chapter.transcription_mode ?? "optimized"} mode with {chapter.transcription_model}.
          </p>
        ) : null}
        {loading ? <p className="muted">Loading chapter data...</p> : null}
      </div>

      {error ? (
        <div className="card error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="card review-toolbar">
        <div className="review-toolbar-main">
          <div className="review-toolbar-fields">
            <label htmlFor="issue-search">Search issues</label>
            <input
              id="issue-search"
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search spoken text, expected text, or context"
            />
          </div>

          <div className="review-toolbar-fields">
            <label htmlFor="issue-type-filter">Issue type</label>
            <select id="issue-type-filter" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="all">All types</option>
              {issueTypeOptions.map(([type, meta]) => (
                <option key={type} value={type}>
                  {meta.label}
                </option>
              ))}
            </select>
          </div>

          <div className="review-toolbar-fields">
            <label htmlFor="transcription-mode">Transcription mode</label>
            <select
              id="transcription-mode"
              value={transcriptionMode}
              onChange={(event) => setTranscriptionMode(event.target.value as TranscriptionMode)}
              disabled={isAnalysisRunning}
            >
              <option value="optimized">Optimized</option>
              <option value="high_quality">High Quality</option>
              <option value="max_quality">Max Quality</option>
            </select>
          </div>

          <div className="review-toolbar-fields">
            <label htmlFor="confidence-filter">Confidence</label>
            <select
              id="confidence-filter"
              value={confidenceFilter}
              onChange={(event) => setConfidenceFilter(event.target.value as ConfidenceFilter)}
            >
              <option value="all">All confidence levels</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        <div className="review-toolbar-actions">
          <input
            ref={replacementAudioInputRef}
            type="file"
            accept=".wav,audio/wav"
            onChange={handleReplacementAudioChange}
            className="hidden-file-input"
            aria-label="Replace chapter WAV"
          />
          <button type="button" onClick={triggerReplacementUpload} disabled={isReplacingAudio}>
            {isReplacingAudio ? "Replacing..." : "Replace WAV"}
          </button>
          <button type="button" onClick={handleAnalyzeChapter} disabled={isAnalysisRunning || !canAnalyze}>
            {isAnalysisRunning ? "Analyzing" : "Analyze Chapter"}
          </button>
          <button type="button" onClick={() => void handleExport("csv")} disabled={isExportingCsv}>
            {isExportingCsv ? "Exporting CSV..." : "Export CSV"}
          </button>
          <button type="button" onClick={() => void handleExport("json")} disabled={isExportingJson}>
            {isExportingJson ? "Exporting JSON..." : "Export JSON"}
          </button>
          <button type="button" onClick={handleAutoEdit} disabled={isAutoEditRunning || !hasAudio}>
            {isAutoEditRunning ? "Exporting" : "Auto Edit"}
          </button>
        </div>
      </div>

      <IssueTimeline
        issues={issues}
        selectedIssueId={selectedIssueId}
        durationMs={chapter?.duration_ms ?? 0}
        onSelect={(issue) => setSelectedIssueId(issue.id)}
      />

      <div className="grid review-grid">
        <div className="review-column">
          <WaveformPanel
            audioUrl={chapter ? getChapterAudioUrl(chapter.id, chapter.analysis_artifact_updated_at) : null}
            hasAudio={hasAudio}
            focusStartMs={selectedIssue?.start_ms}
            focusEndMs={selectedIssue?.end_ms}
            issueType={selectedIssue?.type}
          />

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
        </div>

        <div className="review-column">
          <IssueList
            issues={issues}
            selectedIssueId={selectedIssueId}
            onSelect={(issue) => setSelectedIssueId(issue.id)}
            searchQuery={searchQuery}
            typeFilter={typeFilter}
            confidenceFilter={confidenceFilter}
          />
        </div>

        <div className="review-column">
          <IssueDetail issue={selectedIssue} onStatusChange={handleIssueStatusChange} />
        </div>
      </div>
    </div>
  )
}
