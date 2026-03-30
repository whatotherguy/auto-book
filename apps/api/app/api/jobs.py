from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from ..models import AnalysisJob, Chapter, utc_now
from ..jobs import get_latest_job_for_chapter, is_job_cancelled, request_job_cancellation

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Job already finished")

    request_job_cancellation(job_id)

    # If still queued (not yet picked up by worker), fail immediately
    if job.status == "queued":
        job.status = "failed"
        job.error_message = "Cancelled by user"
        job.finished_at = utc_now()
        chapter = session.get(Chapter, job.chapter_id)
        if chapter and chapter.status not in ("new", "review"):
            chapter.status = "new"
            session.add(chapter)
        session.add(job)
        session.commit()

    return {"ok": True, "job_id": job_id, "status": job.status}


@router.get("/chapters/{chapter_id}/analysis-job")
def get_latest_job_for_chapter_route(
    chapter_id: int,
    session: Session = Depends(get_session),
    type: str | None = Query(default=None),
):
    job = get_latest_job_for_chapter(session, chapter_id, type)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return job
