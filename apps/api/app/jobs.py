from datetime import datetime, timezone
from threading import Thread
from pathlib import Path

from sqlmodel import Session, select

from .db import engine
from .models import AnalysisJob, Chapter
from .services.export import build_auto_edit_export
from .services.storage import ensure_chapter_dirs
from .pipeline.analyze_chapter import run_analysis


def utc_now():
    return datetime.now(timezone.utc)


def set_job_progress(session: Session, job: AnalysisJob, progress: int, step: str) -> None:
    job.status = "running"
    job.progress = progress
    job.current_step = step
    session.add(job)
    session.commit()


def fail_analysis_job(
    session: Session,
    job: AnalysisJob,
    message: str,
    chapter: Chapter | None = None,
) -> None:
    if chapter is not None:
        chapter.status = "new"
        session.add(chapter)

    job.status = "failed"
    job.error_message = message
    job.finished_at = utc_now()
    session.add(job)
    session.commit()


def run_analysis_job(session: Session, job_id: int, transcription_mode: str = "optimized") -> None:
    job = session.get(AnalysisJob, job_id)
    if not job:
        return

    chapter = session.get(Chapter, job.chapter_id)
    if not chapter:
        fail_analysis_job(session, job, "Chapter not found")
        return

    job.started_at = utc_now()
    session.add(job)
    session.commit()

    try:
        run_analysis(session, chapter, job, transcription_mode=transcription_mode)
        if job.status != "completed":
            fail_analysis_job(session, job, "Analysis ended without completing.", chapter)
            return

        job.finished_at = utc_now()
        session.add(job)
        session.commit()
    except Exception as exc:
        fail_analysis_job(session, job, str(exc), chapter)
        return


def run_auto_edit_job(session: Session, job_id: int) -> None:
    job = session.get(AnalysisJob, job_id)
    if not job:
        return

    chapter = session.get(Chapter, job.chapter_id)
    if not chapter:
        fail_analysis_job(session, job, "Chapter not found")
        return

    job.started_at = utc_now()
    session.add(job)
    session.commit()

    try:
        audio_path = None
        if chapter.audio_file_path:
            audio_path = chapter.audio_file_path

        if not audio_path:
            dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
            wav_files = sorted(
                path for folder in (dirs["source"], dirs["working"]) for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() == ".wav"
            )
            if wav_files:
                audio_path = str(wav_files[0])

        if not audio_path:
            fail_analysis_job(session, job, "Audio must be uploaded before running Auto Edit", chapter)
            return

        set_job_progress(session, job, 25, "prepare_export")
        dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
        target_path = dirs["exports"] / "chapter.auto-edited.wav"

        set_job_progress(session, job, 65, "render_export")
        build_auto_edit_export(
            session=session,
            chapter=chapter,
            source_audio_path=Path(chapter.audio_file_path) if chapter.audio_file_path else Path(audio_path),
            target_path=target_path,
        )

        set_job_progress(session, job, 100, "done")
        job.status = "completed"
        job.finished_at = utc_now()
        session.add(job)
        session.commit()
    except Exception as exc:
        fail_analysis_job(session, job, str(exc), chapter)
        return


def start_analysis_job(job_id: int, transcription_mode: str = "optimized") -> None:
    def worker() -> None:
        with Session(engine) as session:
            run_analysis_job(session, job_id, transcription_mode=transcription_mode)

    Thread(target=worker, daemon=True).start()


def start_auto_edit_job(job_id: int) -> None:
    def worker() -> None:
        with Session(engine) as session:
            run_auto_edit_job(session, job_id)

    Thread(target=worker, daemon=True).start()


def get_latest_job_for_chapter(session: Session, chapter_id: int, job_type: str | None = None) -> AnalysisJob | None:
    statement = select(AnalysisJob).where(AnalysisJob.chapter_id == chapter_id)
    if job_type:
        statement = statement.where(AnalysisJob.type == job_type)
    statement = statement.order_by(AnalysisJob.created_at.desc())
    return session.exec(statement).first()
