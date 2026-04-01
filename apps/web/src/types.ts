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

export type IssueStatus = "approved" | "rejected" | "needs_manual"

export type AudioFeatures = {
  rms_db: number
  rms_db_contour: number[]
  spectral_centroid_hz: number
  zero_crossing_rate: number
  onset_strength_max: number
  onset_strength_mean: number
  bandwidth_hz: number
  crest_factor: number
}

export type ProsodyFeatures = {
  duration_ms: number
  speech_rate_wps: number
  f0_mean_hz: number | null
  f0_std_hz: number | null
  f0_contour: number[]
  energy_contour: number[]
  pause_before_ms: number
  pause_after_ms: number
}

export type AudioSignals = {
  has_click_marker: boolean
  click_marker_confidence: number
  has_abrupt_cutoff: boolean
  has_silence_gap: boolean
  silence_gap_ms: number
  has_onset_burst: boolean
  restart_pattern_detected: boolean
}

export type DetectorOutput = {
  detector_name: string
  score: number
  confidence: number
  reasons: string[]
  features_used: Record<string, number | string | boolean>
  triggered: boolean
}

export type ScoredResult = {
  score: number
  confidence: number
  components: Record<string, number>
  reasons: string[]
  ambiguity_flags: string[]
}

export type CompositeScores = {
  mistake_candidate: ScoredResult
  pickup_candidate: ScoredResult
  performance_quality: ScoredResult
  continuity_fit: ScoredResult
  splice_readiness: ScoredResult
}

export type EditorialRecommendation = {
  action: 'review_mistake' | 'likely_pickup' | 'alt_take_available'
        | 'safe_auto_cut' | 'manual_review_required' | 'no_action'
  priority: 'critical' | 'high' | 'medium' | 'low' | 'info'
  reasoning: string
  confidence: number
  related_issue_ids: number[]
}

export type RankedTake = {
  issue_id: number | null
  issue_index: number
  rank: number
  total_score: number
  performance_quality: number
  continuity_fit: number
  text_accuracy: number
  splice_readiness: number
  reasons: string[]
}

export type TakeRanking = {
  cluster_id: string
  ranked_takes: RankedTake[]
  preferred_take_issue_id: number | null
  selection_reasons: string[]
  confidence: number
}

export type AudioSignalRecord = {
  id: number
  chapter_id: number
  signal_type: 'click_marker' | 'abrupt_cutoff' | 'silence_gap' | 'onset_burst'
  start_ms: number
  end_ms: number
  confidence: number
  rms_db: number | null
  spectral_centroid_hz: number | null
  zero_crossing_rate: number | null
  onset_strength: number | null
  bandwidth_hz: number | null
  note: string | null
}

export type VadSegmentRecord = {
  id: number
  chapter_id: number
  start_ms: number
  end_ms: number
  speech_probability: number
}

export type AltTakeCluster = {
  id: number
  chapter_id: number
  manuscript_start_idx: number
  manuscript_end_idx: number
  manuscript_text: string
  preferred_issue_id: number | null
  confidence: number
  members: AltTakeMember[]
  ranking?: TakeRanking | null
}

export type AltTakeMember = {
  id: number
  cluster_id: number
  issue_id: number
  take_order: number
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
  status: IssueStatus
  triage_verdict?: string | null
  triage_reason?: string | null
  audio_features?: AudioFeatures | null
  audio_signals?: AudioSignals | null
  prosody_features?: ProsodyFeatures | null
  alt_take_cluster_id?: number | null
  composite_scores?: CompositeScores | null
  recommendation?: EditorialRecommendation | null
}

export type IssueType =
  | 'false_start' | 'repetition' | 'pickup_restart' | 'substitution'
  | 'missing_text' | 'long_pause' | 'uncertain_alignment'
  | 'pickup_candidate' | 'alt_take' | 'performance_variant' | 'non_speech_marker'

export type AnalysisJob = {
  id: number
  chapter_id: number
  type: string
  status: string
  progress: number
  current_step?: string | null
  error_message?: string | null
}

export type TranscriptionMode = "optimized" | "high_quality" | "max_quality" | "whisper_api"

export type GpuInfo = {
  available: boolean
  device: string
  compute_type: string
  name: string | null
  vram_gb: number | null
}

export type HealthStatus = {
  ok: boolean
  app: string
  ffmpeg_available: boolean
  ffprobe_available: boolean
  gpu: GpuInfo
  has_openai_key: boolean
  has_anthropic_key: boolean
  transcription_backend: string
  llm_provider: string
}

export type GpuThermalStatus = {
  temperature_c: number | null
  power_draw_w: number | null
  utilization_pct: number | null
  monitoring_available: boolean
}

export type ThermalProtectionSettings = {
  enabled: boolean
  warning_temp_c: number
  critical_temp_c: number
  cooldown_seconds: number
}

export type AppSettings = {
  transcription_backend: string
  llm_provider: string
  has_openai_key: boolean
  has_anthropic_key: boolean
  gpu_available: boolean
  gpu_name: string | null
  gpu_vram_gb: number | null
  whisper_api_available: boolean
  triage_available: boolean
  gpu_thermal: GpuThermalStatus
  thermal_protection: ThermalProtectionSettings
}

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
