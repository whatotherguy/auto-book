export type Project = {
  id: number
  name: string
}

export type Chapter = {
  id: number
  project_id: number
  chapter_number: number
  title?: string | null
  raw_text: string
  normalized_text: string
  audio_file_path?: string | null
  has_audio?: boolean
  text_file_path?: string | null
  duration_ms?: number | null
  status: string
  transcript_source?: string | null
  transcript_warnings?: string[]
  transcription_mode?: string | null
  transcription_profile?: string | null
  transcription_model?: string | null
  analysis_artifact_updated_at?: number | null
}

export type Issue = {
  id: number
  chapter_id: number
  type: string
  start_ms: number
  end_ms: number
  confidence: number
  expected_text: string
  spoken_text: string
  context_before: string
  context_after: string
  note?: string | null
  status: string
}

export type AnalysisJob = {
  id: number
  chapter_id: number
  type: string
  status: string
  progress: number
  current_step?: string | null
  error_message?: string | null
}

export type TranscriptionMode = "optimized" | "high_quality" | "max_quality"

export type AcxCheck = {
  measured_at: string
  file_path: string
  passes_acx: boolean
  format: {
    container: string
    sample_rate_hz: number
    channels: number
    bit_depth: number
    duration_ms: number
  }
  levels: {
    peak_dbfs: number
    rms_dbfs: number
    estimated_noise_floor_dbfs?: number | null
    noise_floor_note: string
    clipped_sample_count: number
  }
  checks: Array<{
    name: string
    status: string
    actual: string
    target: string
    summary: string
    suggestion?: string | null
  }>
  fix_suggestions: string[]
  notes: string[]
}
