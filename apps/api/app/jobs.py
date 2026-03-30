from threading import Lock, Thread
from pathlib import Path

from sqlmodel import Session, select

from .db import engine
from .models import AnalysisJob, Chapter, utc_now
from .services.export import build_auto_edit_export
from .services.storage import ensure_chapter_dirs
from .pipeline.analyze_chapter import run_analysis

# Cooperative cancellation: set of job IDs that have been requested to cancel.
# Workers check this periodically and abort if their job ID appears.
_cancel_lock = Lock()
_cancelled_jobs: set[int] = set()


def request_job_cancellation(job_id: int) -> None:
    with _cancel_lock:
        _cancelled_jobs.add(job_id)


def is_job_cancelled(job_id: int) -> bool:
    with _cancel_lock:
        return job_id in _cancelled_jobs


def _clear_cancellation(job_id: int) -> None:
    with _cancel_lock:
        _cancelled_jobs.discard(job_id)


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


class JobCancelledError(Exception):
    pass


def run_analysis_job(session: Session, job_id: int, transcription_mode: str = "optimized", force_retranscribe: bool = False, enable_llm_triage: bool = True) -> None:
    job = session.get(AnalysisJob, job_id)
    if not job:
        return

    if is_job_cancelled(job_id):
        fail_analysis_job(session, job, "Cancelled by user")
        _clear_cancellation(job_id)
        return

    chapter = session.get(Chapter, job.chapter_id)
    if not chapter:
        fail_analysis_job(session, job, "Chapter not found")
        return

    job.started_at = utc_now()
    session.add(job)
    session.commit()

    try:
        run_analysis(
            session, chapter, job,
            transcription_mode=transcription_mode,
            force_retranscribe=force_retranscribe,
            cancel_check=lambda: is_job_cancelled(job_id),
            enable_llm_triage=enable_llm_triage,
        )
        if job.status != "completed":
            fail_analysis_job(session, job, "Analysis ended without completing.", chapter)
            return

        job.finished_at = utc_now()
        session.add(job)
        session.commit()
    except JobCancelledError:
        fail_analysis_job(session, job, "Cancelled by user", chapter)
    except Exception as exc:
        fail_analysis_job(session, job, str(exc), chapter)
    finally:
        _clear_cancellation(job_id)


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


def start_analysis_job(job_id: int, transcription_mode: str = "optimized", force_retranscribe: bool = False, enable_llm_triage: bool = True) -> None:
    def worker() -> None:
        with Session(engine) as session:
            run_analysis_job(session, job_id, transcription_mode=transcription_mode, force_retranscribe=force_retranscribe, enable_llm_triage=enable_llm_triage)

    Thread(target=worker, daemon=True).start()


def start_auto_edit_job(job_id: int) -> None:
    def worker() -> None:
        with Session(engine) as session:
            run_auto_edit_job(session, job_id)

    Thread(target=worker, daemon=True).start()


def recover_orphaned_jobs(session: Session) -> int:
    orphaned = session.exec(
        select(AnalysisJob).where(AnalysisJob.status.in_(["queued", "running"]))
    ).all()
    for job in orphaned:
        job.status = "failed"
        job.error_message = "Server restarted while job was in progress"
        job.finished_at = utc_now()
        session.add(job)
    if orphaned:
        session.commit()
    return len(orphaned)


def get_latest_job_for_chapter(session: Session, chapter_id: int, job_type: str | None = None) -> AnalysisJob | None:
    statement = select(AnalysisJob).where(AnalysisJob.chapter_id == chapter_id)
    if job_type:
        statement = statement.where(AnalysisJob.type == job_type)
    statement = statement.order_by(AnalysisJob.created_at.desc())
    return session.exec(statement).first()
