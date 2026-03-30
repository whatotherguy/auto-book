from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Chapter, Issue, utc_now
from ..schemas import IssueUpdate

router = APIRouter(tags=["issues"])


@router.get("/chapters/{chapter_id}/issues")
def list_chapter_issues(chapter_id: int, session: Session = Depends(get_session)):
    statement = select(Issue).where(Issue.chapter_id == chapter_id)
    return session.exec(statement).all()


@router.patch("/issues/{issue_id}")
def update_issue(issue_id: int, payload: IssueUpdate, session: Session = Depends(get_session)):
    issue = session.get(Issue, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    chapter = session.get(Chapter, issue.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if chapter.duration_ms is not None:
        if payload.start_ms is not None and payload.start_ms > chapter.duration_ms:
            raise HTTPException(
                status_code=422,
                detail=f"start_ms must be less than or equal to chapter duration_ms ({chapter.duration_ms})",
            )
        if payload.end_ms is not None and payload.end_ms > chapter.duration_ms:
            raise HTTPException(
                status_code=422,
                detail=f"end_ms must be less than or equal to chapter duration_ms ({chapter.duration_ms})",
            )

    if payload.status is not None:
        issue.status = payload.status
    if payload.note is not None:
        issue.note = payload.note
    if payload.start_ms is not None:
        issue.start_ms = payload.start_ms
    if payload.end_ms is not None:
        issue.end_ms = payload.end_ms

    if issue.start_ms >= issue.end_ms:
        raise HTTPException(status_code=422, detail="start_ms must be less than end_ms")

    issue.updated_at = utc_now()
    session.add(issue)
    session.commit()
    session.refresh(issue)
    return issue
