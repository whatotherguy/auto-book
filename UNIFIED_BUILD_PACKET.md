# Audiobook Editor - Unified Build Packet

## Signal Enhancement + Heuristic Scoring + Calibration

*Merged architecture from two design streams into a single implementation-ready system.*

---

## 1. Unified Architecture Diagram

```
EXISTING PIPELINE (unchanged)
============================================================================
  Upload -> Transcribe -> Tokenize -> Align -> Detect -> [Triage] -> Persist -> Review -> Export
                                        |
                                        v
NEW LAYERS (additive, inserted between Align and Detect)
============================================================================

  Layer 0: Signal Extraction (NEW)
  ┌─────────────────┐   ┌─────────────┐   ┌──────────────────┐
  │ Audio Analyzer   │   │ Silero VAD  │   │ Prosody Analyzer │
  │ (click, cutoff,  │   │ (speech     │   │ (F0, rate,       │
  │  RMS, ZCR, etc.) │   │  boundaries)│   │  energy contour) │
  └────────┬────────┘   └──────┬──────┘   └────────┬─────────┘
           │                   │                    │
           v                   v                    v
  Layer 1: Signal Fusion
  ┌──────────────────────────────────────────────────────────┐
  │              Signal Fusion Layer                          │
  │  Merges audio signals + VAD + prosody into enriched      │
  │  issue records + discovers pickup candidates             │
  └──────────────────────┬───────────────────────────────────┘
                         │
                         v
  EXISTING: Detect Issues (extended to accept enrichment data)
                         │
                         v
  Layer 2: Alt-Take Clustering (NEW)
  ┌──────────────────────────────────────────────────────────┐
  │  Groups overlapping manuscript-span issues into clusters │
  └──────────────────────┬───────────────────────────────────┘
                         │
                         v
  Layer 3: Scoring Engine (NEW)
  ┌──────────────────────────────────────────────────────────┐
  │  a. Build adaptive baseline (chapter/narrator stats)     │
  │  b. Extract RawFeatureCatalog per segment                │
  │  c. Compute DerivedFeatures (z-scores, deltas)           │
  │  d. Run 15 primitive detectors                           │
  │  e. Compute 5 composite scores per segment               │
  │  f. Rank alt-take clusters                               │
  │  g. Generate editorial recommendations                   │
  └──────────────────────┬───────────────────────────────────┘
                         │
                         v
  EXISTING: Triage -> Persist -> Review UI -> Export
  (extended with scoring data, priority sort, alt-take panel)

  Layer 4: Calibration System (OFFLINE, NEW)
  ┌──────────────────────────────────────────────────────────┐
  │  Labeled datasets + synthetic perturbations              │
  │  Monte Carlo sweep over weights/thresholds               │
  │  Outputs CalibrationProfile -> used by Layer 3           │
  └──────────────────────────────────────────────────────────┘
```

---

## 2. Module / Folder Structure

```
apps/api/app/
├── models.py                          # EXTENDED: +6 new tables
├── detection_config.py                # EXTENDED: +signal thresholds, +scoring weights
├── pipeline/
│   └── analyze_chapter.py             # EXTENDED: +6 new pipeline steps
├── services/
│   ├── detect.py                      # EXTENDED: accepts enrichment, +4 issue types
│   ├── export.py                      # EXTENDED: +3 cuttable issue types
│   ├── triage.py                      # UNCHANGED
│   ├── align.py                       # UNCHANGED
│   ├── transcribe.py                  # UNCHANGED
│   │
│   ├── audio_analysis.py              # NEW: RMS, ZCR, centroid, onset, click detection
│   ├── vad.py                         # NEW: Silero VAD speech boundaries
│   ├── prosody.py                     # NEW: F0, rate, energy per token
│   ├── alt_takes.py                   # NEW: alternate take clustering
│   ├── signal_fusion.py              # NEW: merge signals, pickup candidates, enrichment
│   │
│   └── scoring/                       # NEW: entire scoring engine
│       ├── __init__.py
│       ├── pipeline.py                # run_scoring_pipeline() — main entry point
│       ├── features.py                # RawFeatureCatalog extraction
│       ├── derived_features.py        # z-scores, deltas, ratios
│       ├── baseline.py                # AdaptiveBaseline (chapter/narrator stats)
│       ├── detector_output.py         # DetectorOutput, DetectorConfig
│       ├── detector_registry.py       # ALL_DETECTORS list, run_all_detectors()
│       ├── detectors/
│       │   ├── __init__.py
│       │   ├── text.py                # TextMismatch, RepeatedPhrase, SkippedText
│       │   ├── timing.py             # AbnormalPause, RestartGap, RushedDelivery
│       │   ├── audio.py              # ClickTransient, Clipping, RoomToneShift, PunchIn
│       │   ├── prosody.py            # FlatDelivery, WeakLanding, CadenceDrift
│       │   └── context.py            # PickupPattern, ContinuityMismatch
│       ├── composite.py               # 5 composite scoring formulas
│       ├── take_ranking.py            # Alt-take comparison and ranking
│       ├── recommendations.py         # Editorial recommendation engine
│       ├── envelope.py                # SegmentScoringEnvelope
│       └── calibration/
│           ├── __init__.py
│           ├── labels.py              # SegmentLabel, LabeledDataset
│           ├── perturbations.py       # Synthetic defect injection
│           ├── simulation.py          # Monte Carlo weight sweep
│           └── metrics.py             # EvaluationMetrics, evaluate_predictions
│
├── api/
│   ├── chapters.py                    # EXTENDED: +3 new endpoints
│   ├── issues.py                      # UNCHANGED
│   ├── exports.py                     # EXTENDED: new columns in CSV
│   └── calibration.py                 # NEW: calibration management endpoints
│
└── data/
    └── calibration/                   # Labeled datasets stored here
        └── <dataset_name>/
            └── labels.json

apps/web/src/
├── types.ts                           # EXTENDED: scoring types
├── utils.ts                           # EXTENDED: new issue type metadata
├── pages/
│   └── ChapterReviewPage.tsx          # EXTENDED: alt-take panel, priority sort
└── components/
    ├── IssueList.tsx                  # EXTENDED: priority badges, scoring indicators
    ├── IssueDetail.tsx                # EXTENDED: collapsible scoring breakdown
    ├── IssueTimeline.tsx              # EXTENDED: signal marker overlays
    └── AltTakesPanel.tsx              # NEW: alternate take selector
```

---

## 3. Data Model (FINAL)

### 3A. New DB Tables

```python
# models.py — ALL ADDITIONS

class AudioSignal(SQLModel, table=True):
    """Raw audio signal detected at a point in time."""
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    signal_type: str          # "click_marker", "abrupt_cutoff", "silence_gap", "onset_burst"
    start_ms: int
    end_ms: int
    confidence: float
    rms_db: Optional[float] = None
    spectral_centroid_hz: Optional[float] = None
    zero_crossing_rate: Optional[float] = None
    onset_strength: Optional[float] = None
    bandwidth_hz: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class VadSegment(SQLModel, table=True):
    """Speech segment from Silero VAD."""
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    start_ms: int
    end_ms: int
    speech_probability: float
    created_at: datetime = Field(default_factory=utc_now)


class AltTakeCluster(SQLModel, table=True):
    """Group of issues representing alternate takes of the same text span."""
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    manuscript_start_idx: int
    manuscript_end_idx: int
    manuscript_text: str
    preferred_issue_id: Optional[int] = Field(default=None, foreign_key="issue.id")
    confidence: float
    created_at: datetime = Field(default_factory=utc_now)


class AltTakeMember(SQLModel, table=True):
    """Links an issue to an alt-take cluster."""
    id: Optional[int] = Field(default=None, primary_key=True)
    cluster_id: int = Field(foreign_key="alttakecluster.id", index=True)
    issue_id: int = Field(foreign_key="issue.id", index=True)
    take_order: int


class ScoringResult(SQLModel, table=True):
    """Persisted scoring envelope for an issue."""
    id: Optional[int] = Field(default=None, primary_key=True)
    issue_id: int = Field(foreign_key="issue.id", index=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    scoring_version: str = "1.0.0"
    composite_scores_json: str = ""
    detector_outputs_json: str = ""
    recommendation_json: str = ""
    derived_features_json: str = ""
    # Denormalized for fast queries
    mistake_score: float = 0.0
    pickup_score: float = 0.0
    performance_score: float = 0.0
    splice_score: float = 0.0
    priority: str = "info"
    baseline_id: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class CalibrationProfile(SQLModel, table=True):
    """Saved calibration weights from a sweep."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    weights_json: str = ""
    thresholds_json: str = ""
    metrics_json: str = ""
    is_default: bool = False
    created_at: datetime = Field(default_factory=utc_now)
```

### 3B. Issue Table Extensions (Alembic migration)

```python
# New columns on existing Issue table
class Issue(SQLModel, table=True):
    # ... all existing fields unchanged ...

    # Signal features (JSON blobs)
    audio_features_json: Optional[str] = None     # AudioFeatures
    audio_signals_json: Optional[str] = None      # AudioSignals (derived flags)
    prosody_features_json: Optional[str] = None   # ProsodyFeatures

    # Cluster membership
    alt_take_cluster_id: Optional[int] = Field(
        default=None, foreign_key="alttakecluster.id"
    )
```

### 3C. New Issue Types

```
Existing (unchanged):
  false_start, repetition, pickup_restart, substitution,
  missing_text, long_pause, uncertain_alignment

New:
  pickup_candidate      — VAD + audio signals suggest restart without text match
  alt_take              — segment is part of an alternate take cluster
  performance_variant   — same text, different prosody
  non_speech_marker     — click, clap, or intentional edit signal
```

### 3D. TypeScript Types

```typescript
// === Raw feature types (from signal extraction) ===

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

// === Scoring types (from scoring engine) ===

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

// === Extended record types ===

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

// Extended Issue (all new fields optional for backward compat)
export type Issue = {
  // ... all existing fields ...
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
  // New:
  | 'pickup_candidate' | 'alt_take' | 'performance_variant' | 'non_speech_marker'
```

---

## 4. End-to-End Pipeline Flow

```python
def run_analysis(session, chapter, job, ...):
    # === EXISTING (unchanged) ===
    dirs = ensure_chapter_dirs(...)
    set_job_progress(session, job, 10, "prepare_inputs")
    working_audio_path = prepare_working_audio_copy(...)
    manuscript_tokens = build_manuscript_tokens(...)

    set_job_progress(session, job, 35, "transcribe")
    transcript = transcribe_with_whisperx(...)
    spoken_tokens = build_spoken_tokens(transcript)

    set_job_progress(session, job, 55, "align")
    alignment = build_alignment(manuscript_tokens, spoken_tokens)

    # === NEW: Signal Extraction (Layer 0) ===

    set_job_progress(session, job, 60, "audio_analysis")
    audio_signals = analyze_audio_signals(working_audio_path)
    write_json_artifact(dirs["analysis"] / "audio_signals.json", audio_signals)

    set_job_progress(session, job, 63, "vad")
    vad_segments = run_vad(working_audio_path)
    write_json_artifact(dirs["analysis"] / "vad_segments.json", vad_segments)

    set_job_progress(session, job, 66, "prosody")
    prosody_map = extract_prosody(working_audio_path, spoken_tokens)
    write_json_artifact(dirs["analysis"] / "prosody_features.json", prosody_map)

    # === EXISTING (extended): Issue Detection ===

    set_job_progress(session, job, 70, "detect_issues")
    issue_records = build_issue_records(
        chapter=chapter,
        transcript=transcript,
        manuscript_tokens=manuscript_tokens,
        spoken_tokens=spoken_tokens,
        alignment=alignment,
        # NEW optional params — existing callers unaffected
        audio_signals=audio_signals,
        vad_segments=vad_segments,
        prosody_map=prosody_map,
    )

    # === NEW: Signal Fusion (Layer 1) ===

    set_job_progress(session, job, 74, "signal_fusion")
    issue_records = enrich_issues(
        issue_records, audio_signals, vad_segments,
        prosody_map, spoken_tokens, manuscript_tokens, alignment,
    )

    # === NEW: Alt-Take Clustering (Layer 2) ===

    set_job_progress(session, job, 77, "alt_take_clustering")
    alt_take_clusters = detect_alt_takes(
        issue_records, manuscript_tokens, spoken_tokens,
        alignment, prosody_map,
    )
    write_json_artifact(dirs["analysis"] / "alt_take_clusters.json", alt_take_clusters)

    # === NEW: Scoring Engine (Layer 3) ===

    set_job_progress(session, job, 80, "scoring")
    scoring_result = run_scoring_pipeline(
        issue_records=issue_records,
        audio_signals=audio_signals,
        vad_segments=vad_segments,
        prosody_map=prosody_map,
        manuscript_tokens=manuscript_tokens,
        spoken_tokens=spoken_tokens,
        alignment=alignment,
        alt_take_clusters=alt_take_clusters,
        chapter=chapter,
        session=session,
    )
    issue_records = scoring_result["enriched_issues"]
    alt_take_clusters = scoring_result["alt_take_clusters"]
    write_json_artifact(dirs["analysis"] / "scoring_result.json", scoring_result)

    # === EXISTING (unchanged): Triage + Persist ===

    set_job_progress(session, job, 85, "triage_issues")
    # ... LLM triage unchanged ...

    set_job_progress(session, job, 90, "persist")
    persist_issue_models(session, chapter.id, issue_records)
    persist_audio_signals(session, chapter.id, audio_signals)
    persist_vad_segments(session, chapter.id, vad_segments)
    persist_alt_take_clusters(session, chapter.id, alt_take_clusters)
    persist_scoring_results(session, chapter.id, scoring_result)
    # ... rest unchanged ...
```

### Pipeline Progress Map

| Progress | Step                | Compute | Time (30min audio) |
|----------|---------------------|---------|-------------------|
| 10%      | prepare_inputs      | CPU     | <1s               |
| 35%      | transcribe          | GPU     | 3-8 min           |
| 55%      | align               | CPU     | <2s               |
| 60%      | audio_analysis      | CPU     | 15-30s            |
| 63%      | vad                 | GPU (light) | 5-10s         |
| 66%      | prosody             | CPU     | 30-60s            |
| 70%      | detect_issues       | CPU     | <2s               |
| 74%      | signal_fusion       | CPU     | <1s               |
| 77%      | alt_take_clustering | CPU     | <1s               |
| 80%      | scoring             | CPU     | <2s               |
| 85%      | triage_issues       | API     | 5-30s             |
| 90%      | persist             | CPU     | <1s               |

**Total new overhead: ~1-2 minutes** (dominated by prosody/pyin extraction).

---

## 5. Scoring Integration Plan

### How Detectors Feed Scores

```
Signal Extraction Outputs          Existing Detection Outputs
  audio_signals ─────┐               issue_records ────────┐
  vad_segments ──────┤                                      │
  prosody_map ───────┤                                      │
                     │                                      │
                     v                                      v
              ┌──────────────────────────────────────────────────┐
              │  run_scoring_pipeline()                           │
              │                                                   │
              │  Per issue:                                       │
              │    1. Extract RawFeatureCatalog                   │
              │       (alignment_op, match_ratio, text,           │
              │        timing, signal/DSP, prosody, VAD, context) │
              │                                                   │
              │    2. Build AdaptiveBaseline (chapter stats)      │
              │       -> z-scores, percentiles per feature        │
              │                                                   │
              │    3. Compute DerivedFeatures                     │
              │       (z_speech_rate, z_f0, z_energy, deltas,     │
              │        levenshtein_ratio, token_overlap, etc.)    │
              │                                                   │
              │    4. Run 15 Primitive Detectors                  │
              │       Text:    TextMismatch, RepeatedPhrase,      │
              │                SkippedText                        │
              │       Timing:  AbnormalPause, RestartGap,         │
              │                RushedDelivery                     │
              │       Audio:   ClickTransient, Clipping,          │
              │                RoomToneShift, PunchInBoundary     │
              │       Prosody: FlatDelivery, WeakLanding,         │
              │                CadenceDrift                       │
              │       Context: PickupPattern,                     │
              │                ContinuityMismatch                 │
              │       Each -> DetectorOutput(score, confidence,   │
              │                reasons, triggered)                │
              │                                                   │
              │    5. Compute 5 Composite Scores                  │
              │       -> weighted combos of detector outputs      │
              │                                                   │
              │  Per cluster:                                     │
              │    6. Rank alt-takes using composite scores       │
              │                                                   │
              │  Per issue:                                       │
              │    7. Generate EditorialRecommendation             │
              └───────────────────────┬───────────────────────────┘
                                      │
                                      v
```

### How Scores Feed Classifications

```
Composite Scores → Recommendation Engine (deterministic rules):

  splice_readiness > 0.8 + high confidence  → "safe_auto_cut"    (priority: low)
  alt_take cluster with 2+ members          → "alt_take_available" (priority: medium)
  pickup_candidate > 0.6                    → "likely_pickup"     (priority: high/medium)
  mistake_candidate > 0.5                   → "review_mistake"    (priority: critical/high)
  ambiguous (2+ detectors, conflicting)     → "manual_review_required" (priority: medium)
  performance_quality < 0.5                 → "review_mistake"    (priority: low)
  default                                   → "no_action"         (priority: info)
```

### How Classifications Feed UI

```
  Recommendation → Issue.status mapping:
    "safe_auto_cut"           → status: "approved"
    "no_action"               → status: "rejected" (keep in output)
    All others                → status: "needs_manual"

  Recommendation → UI display:
    priority field             → sort order in IssueList
    action field               → badge icon + color
    reasoning                  → tooltip / expandable detail
    related_issue_ids          → cross-linking in alt-take panel
    ambiguity_flags            → warning indicators
```

---

## 6. Calibration System Integration

### Where Simulation Runs

```
Calibration is OFFLINE — it does not run during normal analysis.

  Trigger: Manual (CLI or admin endpoint)

  Input:
    1. LabeledDataset (human-annotated ground truth)
       Stored: data/calibration/<dataset_name>/labels.json
    2. Pre-computed raw features (JSON artifacts from prior analyses)
       Stored: <chapter_dir>/analysis/*.json

  Process:
    1. Load labeled segments + their raw feature artifacts
    2. PerturbationEngine optionally generates synthetic defects
    3. Monte Carlo sweep (default: 1000 iterations):
       a. Sample random weights within configured ranges
       b. Normalize weight groups to sum to 1.0
       c. Re-score all labeled segments with sampled params
       d. Evaluate vs ground truth → EvaluationMetrics
       e. Track best configuration
    4. Output: SweepResult with best config + convergence history
```

### How Weights Are Updated

```
  SweepResult.best_config → CalibrationProfile row in DB

  CalibrationProfile contains:
    weights_json:    {"w_text_mismatch": 0.33, "w_repeated_phrase": 0.18, ...}
    thresholds_json: {"t_text_mismatch": 0.28, "t_abnormal_pause": 0.35, ...}
    metrics_json:    {mistake_f1, pickup_f1, combined_f1, ...}
    is_default: bool

  At analysis time:
    run_scoring_pipeline() loads the CalibrationProfile marked is_default=True.
    If none exists, uses hardcoded SCORING_WEIGHTS_DEFAULT from detection_config.py.
    Weights are injected into composite score formulas.
    Thresholds are injected into DetectorConfig for each detector.
```

### How Configs Are Stored

```
  DB: calibration_profile table
    - Multiple profiles can exist (per narrator, per project, etc.)
    - Exactly one is_default=True at a time
    - Each stores the full parameter set + the metrics achieved

  Filesystem: data/calibration/
    - labels.json files for each labeled dataset
    - Portable: can be shared across environments

  detection_config.py:
    - Hardcoded defaults (MISTAKE_WEIGHTS, PICKUP_WEIGHTS, etc.)
    - Used when no CalibrationProfile exists
    - Serves as documentation of the default configuration
```

---

## 7. UI Integration Plan

### Alt-Take Selector (AltTakesPanel.tsx)

```
┌─────────────────────────────────────────┐
│ Alternate Takes                    [2]  │
├─────────────────────────────────────────┤
│ v "Once upon a time, in a land far..."  │
│   ┌──────────────────────────────────┐  │
│   │ * Take 1  00:02:15 - 00:02:18   │  │  <- preferred (green border)
│   │   Rate: 3.2 wps  Pitch: 142 Hz  │  │
│   │   Quality: 0.87  Fit: 0.91      │  │
│   │   [Play] [Select as preferred]   │  │
│   ├──────────────────────────────────┤  │
│   │   Take 2  00:02:19 - 00:02:22   │  │  <- marked for cut (red border)
│   │   Rate: 4.1 wps  Pitch: 155 Hz  │  │
│   │   Quality: 0.72  Fit: 0.64      │  │
│   │   [Play] [Select as preferred]   │  │
│   └──────────────────────────────────┘  │
│                                         │
│ > "She walked through the garden..."    │
│   2 takes                               │
└─────────────────────────────────────────┘
```

**Behavior:**
- Panel appears in ChapterReviewPage when alt-take clusters exist
- Each cluster is collapsible, shows manuscript text span
- Takes display: prosody stats, composite quality/fit scores, rank
- System auto-selects preferred take (highest ranked); user can override
- Selecting preferred: PATCH `/alt-take-clusters/{id}/preferred` with `{preferred_issue_id}`
  - Preferred take -> status "rejected" (keep in output)
  - Other takes -> status "approved" (marked for cut)
- Uses existing PATCH `/issues/{id}` for status changes — no new issue API needed

### Signal Indicators

**IssueTimeline** — overlay markers for audio signals:
```
Click markers:      small diamond icons at signal position
Abrupt cutoffs:     vertical red dashes
VAD gaps:           gray shading between speech segments
Punch-in points:    vertical dotted lines
```

**IssueList** — new type metadata in utils.ts:
```typescript
pickup_candidate:    { label: "Pickup Candidate",    color: "#5B8DEF", icon: "↩" }
alt_take:            { label: "Alternate Take",       color: "#9B59B6", icon: "⇄" }
performance_variant: { label: "Performance Variant",  color: "#E67E22", icon: "♪" }
non_speech_marker:   { label: "Non-Speech Marker",    color: "#95A5A6", icon: "●" }
```

### Review Prioritization

**IssueList sort order** (default):
```
1. Priority:  critical > high > medium > low > info
2. Within same priority: higher mistake_score first
3. Within same mistake_score: higher pickup_score first
```

**Priority badges** in IssueList rows:
```
critical: red dot
high:     orange dot
medium:   yellow dot
low:      gray dot
info:     no indicator
```

**IssueDetail** — scoring breakdown (collapsible section):
```
[Scoring Details]
  Mistake:     0.82  ████████░░  (text mismatch: 0.35, repeated: 0.20)
  Pickup:      0.15  █░░░░░░░░░
  Quality:     0.71  ███████░░░
  Continuity:  0.88  █████████░
  Splice Safe: 0.79  ████████░░

  Recommendation: review_mistake (critical)
  "Text match ratio: 0.42. Word count ratio: 2.10x expected."

  [Ambiguity] Low Whisper confidence — transcript may be unreliable
```

### New API Endpoints

```
GET   /chapters/{id}/audio-signals          → AudioSignalRecord[]
GET   /chapters/{id}/vad-segments           → VadSegmentRecord[]
GET   /chapters/{id}/alt-take-clusters      → AltTakeCluster[] (with members + ranking)
PATCH /alt-take-clusters/{id}/preferred     → AltTakeCluster
      Body: { preferred_issue_id: int }
GET   /chapters/{id}/scoring-summary        → { envelopes, baseline_stats }
```

---

## 8. Performance Strategy

### GPU vs CPU Split

| Operation              | Compute    | Notes                                        |
|------------------------|------------|----------------------------------------------|
| Whisper transcription  | **GPU**    | Existing, unchanged                          |
| Silero VAD             | **GPU** (light) | Tiny model, runs on same GPU            |
| Audio signal analysis  | **CPU**    | NumPy/FFT — CPU optimal                      |
| Prosody extraction     | **CPU**    | Per-token pyin is the bottleneck              |
| Alt-take clustering    | **CPU**    | Pure logic, no I/O                            |
| Scoring engine         | **CPU**    | Dict operations + arithmetic                  |
| Calibration sweep      | **CPU**    | Offline only, can run on any machine          |

### Batching Strategy

```
Sequential (must complete in order):
  Transcribe -> Align -> [new layers] -> Detect -> Triage -> Persist

Parallelizable within signal extraction:
  audio_analysis + vad can run concurrently (different compute targets)
  prosody must wait for spoken_tokens (from transcription)

Prosody optimization:
  Phase 1: extract only for tokens in detected issue regions
  Phase 2+: expand to full chapter for alt-take comparison
```

### Caching Strategy

```
JSON Artifacts (per-chapter, in analysis/ directory):
  audio_signals.json      — reusable unless audio changes
  vad_segments.json       — reusable unless audio changes
  prosody_features.json   — reusable unless audio changes
  alt_take_clusters.json  — recomputed when issues change
  scoring_result.json     — recomputed when issues or weights change

Baseline caching:
  AdaptiveBaseline stored per-chapter in scoring_result.json
  Narrator-level baseline: aggregated from chapter baselines, cached in DB

Re-analysis optimization:
  If audio hasn't changed, skip signal extraction steps.
  Only rerun scoring when calibration profile updates.
```

---

## 9. Implementation Phases

### Phase 1: Feature + Signal Layer

**Goal:** Extract raw audio features without changing existing behavior.

**Files created:**
- `services/audio_analysis.py` — RMS, ZCR, centroid, onset, click/cutoff detection
- `services/vad.py` — Silero VAD speech boundaries
- `services/prosody.py` — per-token F0, rate, energy

**Files modified:**
- `models.py` — add AudioSignal, VadSegment tables
- `pipeline/analyze_chapter.py` — insert 3 extraction steps (60-66%)
- `requirements.txt` — add librosa

**DB migration:** Create audiosignal, vadsegment tables.

**Validation:** Run analysis on test chapter, verify JSON artifacts generated. Existing issue detection unchanged.

---

### Phase 2: Detectors

**Goal:** Merge signals into enriched issues, add new issue types.

**Files created:**
- `services/signal_fusion.py` — enrich_issues(), detect_pickup_candidates()
- `services/alt_takes.py` — alt-take clustering
- `services/scoring/detector_output.py` — DetectorOutput dataclass
- `services/scoring/detectors/text.py` — TextMismatch, RepeatedPhrase, SkippedText
- `services/scoring/detectors/timing.py` — AbnormalPause, RestartGap, RushedDelivery
- `services/scoring/detectors/audio.py` — ClickTransient, Clipping, RoomToneShift, PunchIn
- `services/scoring/detectors/prosody.py` — FlatDelivery, WeakLanding, CadenceDrift
- `services/scoring/detectors/context.py` — PickupPattern, ContinuityMismatch
- `services/scoring/detector_registry.py` — ALL_DETECTORS, run_all_detectors()

**Files modified:**
- `models.py` — add AltTakeCluster, AltTakeMember + Issue column extensions
- `detection_config.py` — add signal thresholds, detector configs
- `pipeline/analyze_chapter.py` — insert signal_fusion + alt_take_clustering steps
- `services/detect.py` — accept optional enrichment params, add 4 issue types
- `services/export.py` — add new types to CUTTABLE_ISSUE_TYPES
- `apps/web/src/types.ts` — add signal + detector types
- `apps/web/src/utils.ts` — add metadata for new issue types

**DB migration:** Create alttakecluster, alttakemember tables; add columns to issue.

**Validation:** Run analysis, verify new issue types detected, alt-takes clustered. Existing types still detected at same rates.

---

### Phase 3: Scoring

**Goal:** Composite scoring, recommendations, priority ordering.

**Files created:**
- `services/scoring/features.py` — RawFeatureCatalog
- `services/scoring/derived_features.py` — DerivedFeatures, compute_derived_features()
- `services/scoring/baseline.py` — AdaptiveBaseline, build_chapter_baseline()
- `services/scoring/composite.py` — 5 composite score formulas
- `services/scoring/take_ranking.py` — rank_alternate_takes()
- `services/scoring/recommendations.py` — generate_recommendation()
- `services/scoring/envelope.py` — SegmentScoringEnvelope
- `services/scoring/pipeline.py` — run_scoring_pipeline()

**Files modified:**
- `models.py` — add ScoringResult table
- `pipeline/analyze_chapter.py` — insert scoring step at 80%
- `detection_config.py` — add SCORING_WEIGHTS_DEFAULT, composite weight constants
- `apps/web/src/types.ts` — add CompositeScores, EditorialRecommendation types

**DB migration:** Create scoringresult table.

**Validation:** Run analysis, verify scoring envelopes generated. Check recommendation priority ordering makes sense against manually reviewed chapters.

---

### Phase 4: Calibration

**Goal:** Offline calibration harness for tuning weights.

**Files created:**
- `services/scoring/calibration/labels.py` — SegmentLabel, LabeledDataset
- `services/scoring/calibration/perturbations.py` — PerturbationEngine
- `services/scoring/calibration/simulation.py` — run_calibration_sweep()
- `services/scoring/calibration/metrics.py` — EvaluationMetrics
- `api/calibration.py` — admin endpoints

**Files modified:**
- `models.py` — add CalibrationProfile table
- `services/scoring/pipeline.py` — load active CalibrationProfile if available

**DB migration:** Create calibrationprofile table.

**Validation:** Create a small labeled dataset (10-20 segments), run sweep, verify metrics computed and best config stored. Apply profile, re-analyze, verify scores shift.

---

### Phase 5: UI Enhancements

**Goal:** Surface scoring and alt-takes in the review UI.

**Files created:**
- `components/AltTakesPanel.tsx` — alt-take selector

**Files modified:**
- `pages/ChapterReviewPage.tsx` — integrate AltTakesPanel, priority sort
- `components/IssueList.tsx` — priority badges, scoring indicators
- `components/IssueDetail.tsx` — collapsible scoring breakdown
- `components/IssueTimeline.tsx` — signal marker overlays
- `api/chapters.py` — new GET endpoints for signals/clusters/scoring
- `api.ts` — new fetch functions

**Validation:** Visual QA of all new UI elements. Alt-take selection workflow works end-to-end. Priority sort surfaces critical items first.

---

### Phase 6: Auto-Edit Readiness

**Goal:** Enable auto-cut decisions driven by splice_readiness score.

**Files modified:**
- `services/export.py` — use splice_readiness + recommendation to auto-approve cuts
- `api/exports.py` — add optional `auto_approve_threshold` param to edited-wav export
- `components/ChapterReviewPage.tsx` — "Auto-approve safe cuts" button

**Logic:**
```python
# In export pipeline:
if issue.recommendation.action == "safe_auto_cut" and issue.recommendation.confidence > threshold:
    issue.status = "approved"  # auto-approve for cut
```

**Validation:** Compare auto-approved cuts against human-approved cuts on test data. Measure false_auto_cut_rate.

---

## 10. Risks + Edge Cases

### Narrator Variability

**Risk:** Baselines calibrated for one narrator's voice don't generalize.
**Mitigation:**
- Adaptive baseline tiers: chapter -> session -> narrator
- Blending for chapters < 30 segments
- CalibrationProfile can be per-narrator
- Baseline drift detection alerts when stats shift mid-chapter

### Noisy Recordings

**Risk:** High background noise causes false click/cutoff detections.
**Mitigation:**
- Crest factor threshold (12dB) filters out sustained noise
- Spectral centroid filter (>2kHz) separates clicks from low-frequency rumble
- Clipping detector catches saturation before downstream detectors interpret it
- Low SNR flag in baseline → reduces confidence of audio detectors

### Overlapping Speech

**Risk:** Multiple voices (intro, outro, character voices) confuse single-narrator models.
**Mitigation:**
- VAD treats all speech equally; doesn't attempt speaker diarization
- Prosody baseline will have higher variance when character voices present
- z-score normalization naturally accommodates wider ranges
- Known limitation: performance_variant detection is less reliable with character voices

### Ambiguous Takes

**Risk:** Two takes are nearly identical in quality; system picks arbitrarily.
**Mitigation:**
- TakeRanking reports confidence gap between top two takes
- "Close call" flag when gap < 0.05 → UI shows warning
- Tie-breaking: text accuracy -> continuity -> later take (narrator improves)
- User always has final override via AltTakesPanel

### Whisper Transcription Errors

**Risk:** Incorrect transcript causes false text_mismatch detections.
**Mitigation:**
- TextMismatchDetector confidence scaled by whisper_word_confidence
- Low Whisper confidence → ambiguity flag on composite scores
- Short segments (1-2 words) get score reduction
- Scoring engine preserves confidence separately from score

### Edge-of-Chapter Segments

**Risk:** First/last segments have no neighbor for delta features.
**Mitigation:**
- NeighborContext uses chapter-mean values when no neighbor exists
- Continuity detectors skip first/last with reduced weight
- is_first_sentence / is_last_sentence flags suppress certain detectors

### Very Short Chapters

**Risk:** Chapter with < 30 segments has unstable baseline statistics.
**Mitigation:**
- Baseline blending with narrator-level stats when sample_count < 30
- Blend ratio configurable (default: 50/50)
- Prosody detectors mark themselves low-confidence when baseline is blended

### Performance: Long Chapters

**Risk:** pyin prosody extraction on 2-hour chapters is slow.
**Mitigation:**
- Phase 1: compute prosody only for tokens near detected issues
- Capped contour lengths (50 frames) for storage
- concurrent.futures.ThreadPoolExecutor for audio_analysis
- VAD can share GPU with Whisper if run sequentially

### Calibration Overfitting

**Risk:** Monte Carlo sweep overfits to small labeled dataset.
**Mitigation:**
- Monitor convergence_history for plateau
- Compare top-10 configs for stability (should be similar)
- Perturbation engine tests sensitivity to synthetic defects
- Cross-validation on held-out chapters before deploying profile

---

## Appendix A: Alembic Migration

```python
# alembic/versions/xxx_add_signal_scoring_tables.py

def upgrade():
    # --- Signal tables ---
    op.create_table('audiosignal',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
        sa.Column('signal_type', sa.String, nullable=False),
        sa.Column('start_ms', sa.Integer, nullable=False),
        sa.Column('end_ms', sa.Integer, nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('rms_db', sa.Float),
        sa.Column('spectral_centroid_hz', sa.Float),
        sa.Column('zero_crossing_rate', sa.Float),
        sa.Column('onset_strength', sa.Float),
        sa.Column('bandwidth_hz', sa.Float),
        sa.Column('note', sa.String),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_table('vadsegment',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
        sa.Column('start_ms', sa.Integer, nullable=False),
        sa.Column('end_ms', sa.Integer, nullable=False),
        sa.Column('speech_probability', sa.Float, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_table('alttakecluster',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
        sa.Column('manuscript_start_idx', sa.Integer, nullable=False),
        sa.Column('manuscript_end_idx', sa.Integer, nullable=False),
        sa.Column('manuscript_text', sa.String, nullable=False),
        sa.Column('preferred_issue_id', sa.Integer, sa.ForeignKey('issue.id')),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_table('alttakemember',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('cluster_id', sa.Integer, sa.ForeignKey('alttakecluster.id'), index=True),
        sa.Column('issue_id', sa.Integer, sa.ForeignKey('issue.id'), index=True),
        sa.Column('take_order', sa.Integer, nullable=False),
    )

    # --- Scoring tables ---
    op.create_table('scoringresult',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('issue_id', sa.Integer, sa.ForeignKey('issue.id'), index=True),
        sa.Column('chapter_id', sa.Integer, sa.ForeignKey('chapter.id'), index=True),
        sa.Column('scoring_version', sa.String, nullable=False),
        sa.Column('composite_scores_json', sa.String),
        sa.Column('detector_outputs_json', sa.String),
        sa.Column('recommendation_json', sa.String),
        sa.Column('derived_features_json', sa.String),
        sa.Column('mistake_score', sa.Float, default=0.0),
        sa.Column('pickup_score', sa.Float, default=0.0),
        sa.Column('performance_score', sa.Float, default=0.0),
        sa.Column('splice_score', sa.Float, default=0.0),
        sa.Column('priority', sa.String, default='info'),
        sa.Column('baseline_id', sa.String),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_table('calibrationprofile',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('weights_json', sa.String),
        sa.Column('thresholds_json', sa.String),
        sa.Column('metrics_json', sa.String),
        sa.Column('is_default', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )

    # --- Extend Issue table ---
    op.add_column('issue', sa.Column('audio_features_json', sa.String))
    op.add_column('issue', sa.Column('audio_signals_json', sa.String))
    op.add_column('issue', sa.Column('prosody_features_json', sa.String))
    op.add_column('issue', sa.Column('alt_take_cluster_id', sa.Integer,
                                      sa.ForeignKey('alttakecluster.id')))


def downgrade():
    op.drop_column('issue', 'alt_take_cluster_id')
    op.drop_column('issue', 'prosody_features_json')
    op.drop_column('issue', 'audio_signals_json')
    op.drop_column('issue', 'audio_features_json')
    op.drop_table('calibrationprofile')
    op.drop_table('scoringresult')
    op.drop_table('alttakemember')
    op.drop_table('alttakecluster')
    op.drop_table('vadsegment')
    op.drop_table('audiosignal')
```

## Appendix B: Dependency Additions

```
# requirements.txt additions
librosa>=0.10.0          # audio feature extraction, pyin F0
# silero-vad loaded via torch.hub (no pip package needed)
# torchaudio already present (used by whisperx)
# numpy already present
```

No new frontend dependencies — new components use existing React + wavesurfer.js.

## Appendix C: Configuration Defaults

```python
# detection_config.py — ALL ADDITIONS

# === Signal Extraction Thresholds ===
CLICK_MIN_DURATION_MS = 5
CLICK_MAX_DURATION_MS = 80
CLICK_CREST_FACTOR_THRESHOLD = 12.0
CLICK_SPECTRAL_CENTROID_MIN_HZ = 2000
CLICK_ZCR_THRESHOLD = 0.3
CLICK_ONSET_STRENGTH_THRESHOLD = 3.0
ABRUPT_CUTOFF_RMS_DROP_FACTOR = 6.0

# === Signal Fusion Thresholds ===
PICKUP_SILENCE_BEFORE_MS = 300
PICKUP_CLICK_PROXIMITY_MS = 2000
NON_SPEECH_MARKER_CONFIDENCE = 0.90
PICKUP_CANDIDATE_BASE_CONFIDENCE = 0.40

# === Alt-Take Clustering ===
ALT_TAKE_MAX_GAP_MS = 15000
ALT_TAKE_MIN_TEXT_OVERLAP = 0.6
ALT_TAKE_MIN_CLUSTER_SIZE = 2

# === Performance Variant Detection ===
PERFORMANCE_VARIANT_RATE_DIFF = 0.3
PERFORMANCE_VARIANT_F0_DIFF_HZ = 20
PERFORMANCE_VARIANT_ENERGY_RATIO = 1.5

# === Composite Scoring Weights (defaults, overridden by CalibrationProfile) ===
MISTAKE_WEIGHTS = {
    "text_mismatch": 0.35, "repeated_phrase": 0.20, "skipped_text": 0.20,
    "abnormal_pause": 0.10, "rushed_delivery": 0.05, "clipping": 0.05,
    "click_transient": 0.05,
}
PICKUP_WEIGHTS = {
    "pickup_pattern": 0.35, "restart_gap": 0.25, "click_transient": 0.15,
    "repeated_phrase": 0.10, "abnormal_pause": 0.10, "punch_in_boundary": 0.05,
}
PERFORMANCE_WEIGHTS = {
    "flat_delivery": -0.30, "weak_landing": -0.20, "cadence_drift": -0.15,
    "rushed_delivery": -0.15, "clipping": -0.10, "room_tone_shift": -0.10,
}
CONTINUITY_WEIGHTS = {
    "continuity_mismatch": -0.40, "room_tone_shift": -0.25,
    "punch_in_boundary": -0.20, "cadence_drift": -0.15,
}
TAKE_PREFERENCE_WEIGHTS = {
    "text_accuracy": 0.35, "performance_quality": 0.30,
    "continuity_fit": 0.25, "splice_readiness": 0.10,
}

# === Existing thresholds (unchanged) ===
# ISSUE_STATUS_APPROVED_CONFIDENCE_THRESHOLD = 0.85
# ISSUE_STATUS_PENDING_CONFIDENCE_THRESHOLD = 0.70
```
