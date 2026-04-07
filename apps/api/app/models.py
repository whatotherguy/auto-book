from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now, sa_column_kwargs={"onupdate": utc_now})


class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    chapter_number: int
    title: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    audio_file_path: Optional[str] = None
    text_file_path: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str = "new"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now, sa_column_kwargs={"onupdate": utc_now})


class AnalysisJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    type: str = "analyze_chapter"
    status: str = "queued"
    progress: int = 0
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Issue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    type: str
    start_ms: int
    end_ms: int
    confidence: float
    expected_text: str = ""
    spoken_text: str = ""
    context_before: str = ""
    context_after: str = ""
    note: Optional[str] = None
    # DEPRECATED: status field is kept for backward compatibility
    # Use editor_decision and review_state for new code
    status: str = "pending"
    triage_verdict: Optional[str] = None    # "keep", "dismiss", "uncertain", or None
    triage_reason: Optional[str] = None     # LLM explanation
    # New review decision fields (v2)
    # editor_decision: "cut", "keep", "needs_review", or None (untouched)
    editor_decision: Optional[str] = None
    # model_action: "safe_cut", "compare_takes", "review", "ignore"
    model_action: Optional[str] = None
    # review_state: "unreviewed", "reviewed"
    review_state: str = "unreviewed"
    # Signal features (JSON blobs)
    audio_features_json: Optional[str] = None
    audio_signals_json: Optional[str] = None
    prosody_features_json: Optional[str] = None
    # Cluster membership
    alt_take_cluster_id: Optional[int] = Field(
        default=None, foreign_key="alttakecluster.id"
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now, sa_column_kwargs={"onupdate": utc_now})


class AudioSignal(SQLModel, table=True):
    """Raw audio signal detected at a point in time."""
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id", index=True)
    signal_type: str
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
