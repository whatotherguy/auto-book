from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from ..models import AnalysisJob
from ..jobs import get_latest_job_for_chapter

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
