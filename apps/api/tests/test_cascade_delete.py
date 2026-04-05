"""Tests that deleting a chapter or resetting analysis state cleans up
all dependent records (ScoringResult, AltTakeCluster, AltTakeMember,
AudioSignal, VadSegment) and never leaves orphans behind."""

import io
import wave

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.chapters import delete_chapter_dependent_records, reset_chapter_audio_review_state
from app.db import get_session
from app.main import app
from app.models import (
    AltTakeCluster,
    AltTakeMember,
    AnalysisJob,
    AudioSignal,
    Chapter,
    Issue,
    ScoringResult,
    VadSegment,
)
from app.services.storage import ensure_chapter_dirs


def _make_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    SQLModel.metadata.create_all(engine)
    return engine


def _build_wav_bytes(seconds: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * int(44100 * seconds))
    return buf.getvalue()


def _seed_chapter_with_analysis(session: Session, chapter_id: int) -> None:
    """Insert a full set of analysis-derived records for *chapter_id*."""
    issue_a = Issue(chapter_id=chapter_id, type="repetition", start_ms=0, end_ms=100, confidence=0.9)
    issue_b = Issue(chapter_id=chapter_id, type="false_start", start_ms=200, end_ms=300, confidence=0.85)
    session.add(issue_a)
    session.add(issue_b)
    session.flush()  # get IDs

    cluster = AltTakeCluster(
        chapter_id=chapter_id,
        manuscript_start_idx=0,
        manuscript_end_idx=2,
        manuscript_text="hello world",
        preferred_issue_id=issue_a.id,
        confidence=0.8,
    )
    session.add(cluster)
    session.flush()

    issue_a.alt_take_cluster_id = cluster.id
    session.add(issue_a)

    member_a = AltTakeMember(cluster_id=cluster.id, issue_id=issue_a.id, take_order=0)
    member_b = AltTakeMember(cluster_id=cluster.id, issue_id=issue_b.id, take_order=1)
    session.add(member_a)
    session.add(member_b)

    sr_a = ScoringResult(issue_id=issue_a.id, chapter_id=chapter_id)
    sr_b = ScoringResult(issue_id=issue_b.id, chapter_id=chapter_id)
    session.add(sr_a)
    session.add(sr_b)

    session.add(AudioSignal(chapter_id=chapter_id, signal_type="click", start_ms=50, end_ms=60, confidence=0.7))
    session.add(VadSegment(chapter_id=chapter_id, start_ms=0, end_ms=500, speech_probability=0.95))
    session.add(AnalysisJob(chapter_id=chapter_id, status="completed", progress=100))

    session.commit()


def test_delete_chapter_dependent_records_removes_all_related_rows(tmp_path):
    engine = _make_engine(tmp_path)
    with Session(engine) as session:
        chapter = Chapter(project_id=1, chapter_number=1, status="review")
        session.add(chapter)
        session.commit()
        session.refresh(chapter)

        _seed_chapter_with_analysis(session, chapter.id)

        # Sanity: records exist before deletion.
        assert session.exec(select(Issue).where(Issue.chapter_id == chapter.id)).all()
        assert session.exec(select(ScoringResult).where(ScoringResult.chapter_id == chapter.id)).all()
        assert session.exec(select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter.id)).all()
        assert session.exec(select(AltTakeMember)).all()
        assert session.exec(select(AudioSignal).where(AudioSignal.chapter_id == chapter.id)).all()
        assert session.exec(select(VadSegment).where(VadSegment.chapter_id == chapter.id)).all()
        assert session.exec(select(AnalysisJob).where(AnalysisJob.chapter_id == chapter.id)).all()

        delete_chapter_dependent_records(session, chapter.id)
        session.commit()

        assert session.exec(select(Issue).where(Issue.chapter_id == chapter.id)).all() == []
        assert session.exec(select(ScoringResult).where(ScoringResult.chapter_id == chapter.id)).all() == []
        assert session.exec(select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter.id)).all() == []
        assert session.exec(select(AltTakeMember)).all() == []
        assert session.exec(select(AudioSignal).where(AudioSignal.chapter_id == chapter.id)).all() == []
        assert session.exec(select(VadSegment).where(VadSegment.chapter_id == chapter.id)).all() == []
        assert session.exec(select(AnalysisJob).where(AnalysisJob.chapter_id == chapter.id)).all() == []


def test_reset_chapter_audio_review_state_clears_all_analysis_records(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)
    with Session(engine) as session:
        chapter = Chapter(project_id=1, chapter_number=1, status="review", normalized_text="some text")
        session.add(chapter)
        session.commit()
        session.refresh(chapter)

        _seed_chapter_with_analysis(session, chapter.id)
        ensure_chapter_dirs(1, 1)

        reset_chapter_audio_review_state(session, chapter)
        session.commit()
        session.refresh(chapter)

        assert chapter.status == "new"
        assert chapter.normalized_text == ""
        assert session.exec(select(Issue).where(Issue.chapter_id == chapter.id)).all() == []
        assert session.exec(select(ScoringResult).where(ScoringResult.chapter_id == chapter.id)).all() == []
        assert session.exec(select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter.id)).all() == []
        assert session.exec(select(AltTakeMember)).all() == []
        assert session.exec(select(AudioSignal).where(AudioSignal.chapter_id == chapter.id)).all() == []
        assert session.exec(select(VadSegment).where(VadSegment.chapter_id == chapter.id)).all() == []
        assert session.exec(select(AnalysisJob).where(AnalysisJob.chapter_id == chapter.id)).all() == []


def test_delete_chapter_endpoint_removes_all_related_rows(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.db.engine", engine)
    try:
        with TestClient(app) as client:
            project = client.post("/projects", json={"name": "P"}).json()
            chapter = client.post(
                f"/projects/{project['id']}/chapters",
                json={"chapter_number": 1, "title": "C"},
            ).json()
            chapter_id = chapter["id"]

            with Session(engine) as session:
                _seed_chapter_with_analysis(session, chapter_id)

            resp = client.delete(f"/chapters/{chapter_id}")
            assert resp.status_code == 200

            with Session(engine) as session:
                assert session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all() == []
                assert session.exec(select(ScoringResult).where(ScoringResult.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AltTakeMember)).all() == []
                assert session.exec(select(AudioSignal).where(AudioSignal.chapter_id == chapter_id)).all() == []
                assert session.exec(select(VadSegment).where(VadSegment.chapter_id == chapter_id)).all() == []
    finally:
        app.dependency_overrides.clear()


def test_delete_project_endpoint_removes_all_related_rows(tmp_path, monkeypatch):
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.db.engine", engine)
    try:
        with TestClient(app) as client:
            project = client.post("/projects", json={"name": "P"}).json()
            project_id = project["id"]
            chapter = client.post(
                f"/projects/{project_id}/chapters",
                json={"chapter_number": 1, "title": "C"},
            ).json()
            chapter_id = chapter["id"]

            with Session(engine) as session:
                _seed_chapter_with_analysis(session, chapter_id)

            resp = client.delete(f"/projects/{project_id}")
            assert resp.status_code == 200

            with Session(engine) as session:
                assert session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all() == []
                assert session.exec(select(ScoringResult).where(ScoringResult.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AltTakeMember)).all() == []
                assert session.exec(select(AudioSignal).where(AudioSignal.chapter_id == chapter_id)).all() == []
                assert session.exec(select(VadSegment).where(VadSegment.chapter_id == chapter_id)).all() == []
    finally:
        app.dependency_overrides.clear()


def test_reuploading_audio_after_analysis_resets_all_records(tmp_path, monkeypatch):
    """Re-uploading audio after a full analysis (which creates ScoringResult etc.)
    must succeed and leave no orphaned records."""
    data_root = tmp_path / "projects"
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.settings.data_root", data_root)

    engine = _make_engine(tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.db.engine", engine)
    try:
        with TestClient(app) as client:
            project = client.post("/projects", json={"name": "P"}).json()
            chapter = client.post(
                f"/projects/{project['id']}/chapters",
                json={"chapter_number": 1, "title": "C"},
            ).json()
            chapter_id = chapter["id"]

            # Upload initial audio.
            first = client.post(
                f"/chapters/{chapter_id}/audio",
                files={"file": ("take1.wav", _build_wav_bytes(), "audio/wav")},
            )
            assert first.status_code == 200

            # Simulate a completed analysis by inserting all derived records.
            with Session(engine) as session:
                _seed_chapter_with_analysis(session, chapter_id)

            # Re-upload audio — this calls reset_chapter_audio_review_state
            # which must delete all derived records without FK errors.
            second = client.post(
                f"/chapters/{chapter_id}/audio",
                files={"file": ("take2.wav", _build_wav_bytes(), "audio/wav")},
            )
            assert second.status_code == 200

            with Session(engine) as session:
                assert session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all() == []
                assert session.exec(select(ScoringResult).where(ScoringResult.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AltTakeCluster).where(AltTakeCluster.chapter_id == chapter_id)).all() == []
                assert session.exec(select(AltTakeMember)).all() == []
                assert session.exec(select(AudioSignal).where(AudioSignal.chapter_id == chapter_id)).all() == []
                assert session.exec(select(VadSegment).where(VadSegment.chapter_id == chapter_id)).all() == []
    finally:
        app.dependency_overrides.clear()
