from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

# New decision/state types for v2 review model
EditorDecision = Literal["cut", "keep", "needs_review"]
ModelAction = Literal["safe_cut", "compare_takes", "review", "ignore"]
ReviewState = Literal["unreviewed", "reviewed"]
# Legacy status type (deprecated)
LegacyStatus = Literal["approved", "rejected", "needs_manual", "pending"]


class ProjectCreate(BaseModel):
    name: str


class ChapterCreate(BaseModel):
    chapter_number: int = Field(ge=1)
    title: Optional[str] = None


class ChapterTextUpdate(BaseModel):
    raw_text: str


class AnalyzeChapterRequest(BaseModel):
    transcription_mode: str = "optimized"
    force_retranscribe: bool = False
    enable_llm_triage: bool = True  # Run LLM false-positive filtering if API key is configured

    @model_validator(mode="after")
    def validate_mode(self) -> "AnalyzeChapterRequest":
        allowed_modes = {"optimized", "high_quality", "max_quality", "whisper_api"}
        if self.transcription_mode not in allowed_modes:
            raise ValueError("transcription_mode must be one of: optimized, high_quality, max_quality, whisper_api")
        return self


class IssueUpdate(BaseModel):
    # Legacy status field (deprecated, kept for compatibility)
    status: Optional[LegacyStatus] = None
    # New v2 decision fields
    editor_decision: Optional[EditorDecision] = None
    review_state: Optional[ReviewState] = None
    # Other fields
    note: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "IssueUpdate":
        if self.start_ms is not None and self.start_ms < 0:
            raise ValueError("start_ms must be non-negative")

        if self.end_ms is not None and self.end_ms < 0:
            raise ValueError("end_ms must be non-negative")

        if self.start_ms is not None and self.end_ms is not None and self.start_ms >= self.end_ms:
            raise ValueError("start_ms must be less than end_ms")

        return self


class IssueBatchUpdate(BaseModel):
    issue_ids: list[int] = Field(min_length=1)
    # Legacy status field (deprecated, kept for compatibility)
    status: Optional[LegacyStatus] = None
    # New v2 decision fields
    editor_decision: Optional[EditorDecision] = None
    review_state: Optional[ReviewState] = None
    # Other fields
    note: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "IssueBatchUpdate":
        if (
            self.status is None
            and self.note is None
            and self.editor_decision is None
            and self.review_state is None
        ):
            raise ValueError("At least one of 'status', 'editor_decision', 'review_state', or 'note' must be provided")
        return self


class AnalyzeResponse(BaseModel):
    job_id: int
    status: str
