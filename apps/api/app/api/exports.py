import csv
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..api.chapters import sync_chapter_audio_path
from ..db import get_session
from ..jobs import start_auto_edit_job
from ..models import AnalysisJob, Chapter, Issue, ScoringResult
from ..services.export import build_auto_edit_export
from ..services.storage import ensure_chapter_dirs
from ..utils.timecode import ms_to_timecode

router = APIRouter(tags=["exports"])


@router.post("/chapters/{chapter_id}/exports/csv")
def export_csv(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    issues = session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all()
    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    target = dirs["exports"] / "issues.csv"

    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "issue_id",
            "type",
            "start_timecode",
            "end_timecode",
            "confidence",
            "expected_text",
            "spoken_text",
            "status",
            "note",
            "priority",
            "mistake_score",
            "pickup_score",
            "performance_score",
            "splice_score",
        ])

        # Pre-fetch scoring results
        scoring_map: dict[int, ScoringResult] = {}
        scoring_results = session.exec(
            select(ScoringResult).where(ScoringResult.chapter_id == chapter_id)
        ).all()
        for sr in scoring_results:
            scoring_map[sr.issue_id] = sr

        for issue in issues:
            sr = scoring_map.get(issue.id)
            writer.writerow([
                issue.id,
                issue.type,
                ms_to_timecode(issue.start_ms),
                ms_to_timecode(issue.end_ms),
                issue.confidence,
                issue.expected_text,
                issue.spoken_text,
                issue.status,
                issue.note or "",
                sr.priority if sr else "",
                round(sr.mistake_score, 4) if sr else "",
                round(sr.pickup_score, 4) if sr else "",
                round(sr.performance_score, 4) if sr else "",
                round(sr.splice_score, 4) if sr else "",
            ])

    return FileResponse(path=target, filename="issues.csv", media_type="text/csv")


@router.post("/chapters/{chapter_id}/exports/json")
def export_json(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    issues = session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all()
    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    target = dirs["exports"] / "issues.json"

    payload = [
        {
            "id": issue.id,
            "type": issue.type,
            "start_ms": issue.start_ms,
            "end_ms": issue.end_ms,
            "confidence": issue.confidence,
            "expected_text": issue.expected_text,
            "spoken_text": issue.spoken_text,
            "context_before": issue.context_before,
            "context_after": issue.context_after,
            "status": issue.status,
            "note": issue.note,
        }
        for issue in issues
    ]
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return FileResponse(path=target, filename="issues.json", media_type="application/json")


@router.post("/chapters/{chapter_id}/exports/edited-wav")
def export_edited_wav(chapter_id: int, auto_approve_threshold: float | None = None, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    audio_path = sync_chapter_audio_path(session, chapter)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not uploaded")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    target = dirs["exports"] / "chapter.auto-edited.wav"

    try:
        build_auto_edit_export(
            session=session,
            chapter=chapter,
            source_audio_path=audio_path,
            target_path=target,
            auto_approve_threshold=auto_approve_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileResponse(path=target, filename=target.name, media_type="audio/wav")


@router.post("/chapters/{chapter_id}/exports/edited-wav-job")
def start_edited_wav_export(chapter_id: int, session: Session = Depends(get_session)):
    chapter = session.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    audio_path = sync_chapter_audio_path(session, chapter)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio not uploaded")

    dirs = ensure_chapter_dirs(chapter.project_id, chapter.chapter_number)
    target = dirs["exports"] / "chapter.auto-edited.wav"
    job = AnalysisJob(chapter_id=chapter_id, type="export_edited_wav", status="queued", progress=0)
    session.add(job)
    session.commit()
    session.refresh(job)

    start_auto_edit_job(job.id)

    return {"job_id": job.id, "status": job.status, "output_path": str(target)}
