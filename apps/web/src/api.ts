import { AcxCheck, AltTakeCluster, AnalysisJob, AppSettings, AudioSignalRecord, Chapter, EditorDecision, HealthStatus, Issue, Project, ReviewState, TranscriptionMode, VadSegmentRecord } from "./types"

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000"

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function getChapterAudioUrl(chapterId: number, revision?: string | number | null) {
  if (revision == null) {
    return `${API_BASE}/chapters/${chapterId}/audio-file`
  }

  return `${API_BASE}/chapters/${chapterId}/audio-file?rev=${encodeURIComponent(String(revision))}`
}

export function getExportUrl(chapterId: number, kind: "csv" | "json") {
  return `${API_BASE}/chapters/${chapterId}/exports/${kind}`
}

export function getHealth() {
  return fetchJson<HealthStatus>("/health")
}

export function cancelJob(jobId: number) {
  return fetchJson<{ ok: boolean; job_id: number; status: string }>(`/jobs/${jobId}/cancel`, {
    method: "POST"
  })
}

export function getProjects() {
  return fetchJson<Project[]>("/projects")
}

export function getProject(projectId: number) {
  return fetchJson<Project>(`/projects/${projectId}`)
}

export function createProject(name: string) {
  return fetchJson<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  })
}

export function deleteProject(projectId: number) {
  return fetchJson<{ ok: boolean; deleted_project_id: number }>(`/projects/${projectId}`, {
    method: "DELETE"
  })
}

export function getProjectChapters(projectId: number) {
  return fetchJson<Chapter[]>(`/projects/${projectId}/chapters`)
}

export function createChapter(projectId: number, chapterNumber: number, title?: string) {
  return fetchJson<Chapter>(`/projects/${projectId}/chapters`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chapter_number: chapterNumber, title })
  })
}

export function deleteChapter(chapterId: number) {
  return fetchJson<{ ok: boolean; deleted_chapter_id: number }>(`/chapters/${chapterId}`, {
    method: "DELETE"
  })
}

export function uploadChapterAudio(chapterId: number, file: File) {
  const formData = new FormData()
  formData.append("file", file)

  return fetchJson<Chapter & { ok: boolean }>(`/chapters/${chapterId}/audio`, {
    method: "POST",
    body: formData
  })
}

export function uploadChapterAudioWithProgress(
  chapterId: number,
  file: File,
  onProgress: (progress: number) => void
) {
  return new Promise<Chapter & { ok: boolean }>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_BASE}/chapters/${chapterId}/audio`)
    xhr.responseType = "json"

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        return
      }

      onProgress(Math.round((event.loaded / event.total) * 100))
    }

    xhr.onerror = () => {
      reject(new Error("Failed to upload chapter WAV."))
    }

    xhr.onabort = () => {
      reject(new Error("Upload was aborted."))
    }

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error((xhr.response && xhr.response.detail) || `Upload failed: ${xhr.status}`))
        return
      }

      resolve(xhr.response as Chapter & { ok: boolean })
    }

    const formData = new FormData()
    formData.append("file", file)
    xhr.send(formData)
  })
}

export function uploadChapterTextFile(chapterId: number, file: File) {
  const formData = new FormData()
  formData.append("file", file)

  return fetchJson<Chapter>(`/chapters/${chapterId}/text-file`, {
    method: "POST",
    body: formData
  })
}

export function uploadChapterText(chapterId: number, rawText: string) {
  return fetchJson<Chapter>(`/chapters/${chapterId}/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText })
  })
}

export function getChapter(chapterId: number) {
  return fetchJson<Chapter>(`/chapters/${chapterId}`)
}

export function getIssues(chapterId: number) {
  return fetchJson<Issue[]>(`/chapters/${chapterId}/issues`)
}

export function getIssueStats(chapterId: number) {
  return fetchJson<{
    total: number
    reviewed: number
    by_status: Record<string, number>
    by_type: Record<string, number>
    by_confidence: { high: number; medium: number; low: number }
    // New v2 fields
    by_review_state?: Record<string, number>
    by_editor_decision?: Record<string, number>
    by_model_action?: Record<string, number>
  }>(`/chapters/${chapterId}/issues/stats`)
}

export function batchUpdateIssues(
  issueIds: number[],
  payload: {
    status?: Issue["status"]
    editor_decision?: EditorDecision
    review_state?: ReviewState
    note?: string
  }
) {
  return fetchJson<Issue[]>("/issues/batch-update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ issue_ids: issueIds, ...payload }),
  })
}

export function analyzeChapter(chapterId: number, transcriptionMode: TranscriptionMode, forceRetranscribe: boolean = false, enableLlmTriage: boolean = true) {
  return fetchJson<{ job_id: number; status: string }>(`/chapters/${chapterId}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcription_mode: transcriptionMode, force_retranscribe: forceRetranscribe, enable_llm_triage: enableLlmTriage })
  })
}

export function getLatestAnalysisJob(chapterId: number, type?: string) {
  const suffix = type ? `?type=${encodeURIComponent(type)}` : ""
  return fetchJson<AnalysisJob>(`/chapters/${chapterId}/analysis-job${suffix}`)
}

export function getJob(jobId: number) {
  return fetchJson<AnalysisJob>(`/jobs/${jobId}`)
}

export function getAcxCheck(chapterId: number) {
  return fetchJson<AcxCheck | null>(`/chapters/${chapterId}/acx-check`)
}

export function runAcxCheck(chapterId: number) {
  return fetchJson<AcxCheck>(`/chapters/${chapterId}/acx-check`, {
    method: "POST"
  })
}

export function startAutoEditJob(chapterId: number) {
  return fetchJson<{ job_id: number; status: string; output_path: string }>(`/chapters/${chapterId}/exports/edited-wav-job`, {
    method: "POST"
  })
}

export async function downloadChapterExport(chapterId: number, kind: "csv" | "json") {
  const response = await fetch(`${API_BASE}/chapters/${chapterId}/exports/${kind}`, {
    method: "POST"
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Export failed: ${response.status}`)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `issues.${kind}`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function downloadEditedChapterAudio(chapterId: number) {
  const response = await fetch(`${API_BASE}/chapters/${chapterId}/exports/edited-wav`, {
    method: "POST"
  })

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Edited WAV export failed: ${response.status}`)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = "chapter.auto-edited.wav"
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function getSettings() {
  return fetchJson<AppSettings>("/settings")
}

export function updateSettings(payload: {
  openai_api_key?: string
  anthropic_api_key?: string
  llm_provider?: string
  transcription_backend?: string
  gpu_thermal_protection?: boolean
  gpu_temp_warning?: number
  gpu_temp_critical?: number
  gpu_cooldown_seconds?: number
}) {
  return fetchJson<AppSettings>("/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
}

export function getGpuStatus() {
  return fetchJson<{
    available: boolean
    device: string
    compute_type: string
    name: string | null
    vram_gb: number | null
    temperature_c: number | null
    power_draw_w: number | null
    utilization_pct: number | null
    monitoring_available: boolean
    thermal_protection_enabled: boolean
  }>("/settings/gpu-status")
}

export function getSpokenTokens(chapterId: number) {
  return fetchJson<any[]>(`/chapters/${chapterId}/spoken-tokens`)
}

export function updateIssue(
  issueId: number,
  payload: Partial<Pick<Issue, "status" | "editor_decision" | "review_state" | "note" | "start_ms" | "end_ms">>
) {
  return fetchJson<Issue>(`/issues/${issueId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
}

export function getAudioSignals(chapterId: number) {
  return fetchJson<AudioSignalRecord[]>(`/chapters/${chapterId}/audio-signals`)
}

export function getVadSegments(chapterId: number) {
  return fetchJson<VadSegmentRecord[]>(`/chapters/${chapterId}/vad-segments`)
}

export function getAltTakeClusters(chapterId: number) {
  return fetchJson<AltTakeCluster[]>(`/chapters/${chapterId}/alt-take-clusters`)
}

export function setPreferredTake(clusterId: number, preferredIssueId: number) {
  return fetchJson<AltTakeCluster>(`/alt-take-clusters/${clusterId}/preferred`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preferred_issue_id: preferredIssueId })
  })
}

export function getScoringSummary(chapterId: number) {
  return fetchJson<{ envelopes: any[]; baseline_stats: any }>(`/chapters/${chapterId}/scoring-summary`)
}
