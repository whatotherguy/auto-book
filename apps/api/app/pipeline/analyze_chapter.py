from __future__ import annotations

import logging

from sqlmodel import Session

from ..models import AnalysisJob, Chapter

logger = logging.getLogger(__name__)
from ..services.align import build_alignment, build_manuscript_tokens, build_spoken_tokens
from ..services.audio import read_wav_duration_ms
from ..services.detect import build_issue_records, persist_issue_models
from ..services.ingest import prepare_working_audio_copy, write_json_artifact
from ..services.storage import ensure_chapter_dirs
from ..services.text_normalize import normalize_text
from ..services.transcribe import transcribe_with_whisperx


def set_job_progress(session: Session, job: AnalysisJob, progress: int, step: str) -> None:
    job.status = "running"
    job.progress = progress
    job.current_step = step
    session.add(job)
    session.commit()


def make_transcribe_progress_callback(session: Session, job: AnalysisJob):
    def callback(step: str, progress: int, message: str) -> None:
        job.status = "running"
        job.progress = progress
        job.current_step = step
        job.error_message = None
        session.add(job)
        session.commit()

    return callback


def run_analysis(
    session: Session,
    chapter: Chapter,
    job: AnalysisJob,
    transcription_mode: str = "optimized",
    force_retranscribe: bool = False,
    cancel_check: callable = None,
    enable_llm_triage: bool = True,
) -> None:
    from ..jobs import JobCancelledError

    def check_cancelled() -> None:
        if cancel_check and cancel_check():
            raise JobCancelledError("Job cancelled by user")

    try:
        dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)

        set_job_progress(session, job, 10, "prepare_inputs")
        check_cancelled()

        working_audio_path = prepare_working_audio_copy(chapter.audio_file_path, dirs["working"])
        chapter.duration_ms = read_wav_duration_ms(working_audio_path)
        chapter.normalized_text = normalize_text(chapter.raw_text)
        session.add(chapter)
        session.commit()

        manuscript_tokens = build_manuscript_tokens(chapter.raw_text)
        write_json_artifact(dirs["analysis"] / "manuscript_tokens.json", manuscript_tokens)

        set_job_progress(session, job, 35, "transcribe")
        check_cancelled()

        cache_path = dirs["analysis"] / "transcript.raw.json" if not force_retranscribe else None
        transcript = transcribe_with_whisperx(
            working_audio_path,
            manuscript_text=chapter.raw_text,
            duration_ms=chapter.duration_ms,
            progress_callback=make_transcribe_progress_callback(session, job),
            transcription_mode=transcription_mode,
            cache_path=cache_path,
        )
        write_json_artifact(dirs["analysis"] / "transcript.raw.json", transcript)

        if transcript.get("is_placeholder") is True:
            job.status = "failed"
            job.error_message = (
                "Transcription unavailable: WhisperX/faster-whisper is not installed. Install it to run analysis."
            )
            session.add(job)
            session.commit()
            return

        check_cancelled()

        spoken_tokens = build_spoken_tokens(transcript)
        write_json_artifact(dirs["analysis"] / "spoken_tokens.json", spoken_tokens)

        set_job_progress(session, job, 60, "align")
        check_cancelled()

        alignment = build_alignment(manuscript_tokens, spoken_tokens)
        write_json_artifact(dirs["analysis"] / "alignment.json", alignment)

        set_job_progress(session, job, 80, "detect_issues")
        check_cancelled()

        issue_records = build_issue_records(
            chapter=chapter,
            transcript=transcript,
            manuscript_tokens=manuscript_tokens,
            spoken_tokens=spoken_tokens,
            alignment=alignment,
        )

        # Optional LLM triage to filter false positives
        if enable_llm_triage:
            from ..services.triage import is_triage_available, triage_issues

            if is_triage_available():
                set_job_progress(session, job, 85, "triage_issues")
                check_cancelled()
                try:
                    issue_records = triage_issues(issue_records, chapter.raw_text)
                except Exception as exc:
                    logger.warning("LLM triage failed, continuing without: %s", exc)

        write_json_artifact(dirs["analysis"] / "issues.json", issue_records)

        persist_issue_models(session, chapter.id, issue_records)

        chapter.status = "review"
        session.add(chapter)
        session.commit()

        job.status = "completed"
        job.progress = 100
        job.current_step = "done"
        session.add(job)
        session.commit()
    finally:
        if job.status == "running":
            chapter.status = "new"
            job.status = "failed"
            job.error_message = job.error_message or "Analysis did not complete."
            session.add(chapter)
            session.add(job)
            session.commit()
