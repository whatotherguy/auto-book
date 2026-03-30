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
    updated_at: datetime = Field(default_factory=utc_now)


class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True)
    chapter_number: int
    title: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    audio_file_path: Optional[str] = None
    text_file_path: Optional[str] = None
    duration_ms: Optional[int] = None
    status: str = "new"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalysisJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(index=True)
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
    chapter_id: int = Field(index=True)
    type: str
    start_ms: int
    end_ms: int
    confidence: float
    expected_text: str = ""
    spoken_text: str = ""
    context_before: str = ""
    context_after: str = ""
    note: Optional[str] = None
    status: str = "approved"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
