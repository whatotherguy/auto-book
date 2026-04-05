from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Chapter, Issue, utc_now
from ..schemas import IssueBatchUpdate, IssueUpdate

router = APIRouter(tags=["issues"])

# Confidence band thresholds — must match the bands defined in AGENTS.md and the frontend utils.
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.65


@router.get("/chapters/{chapter_id}/issues")
def list_chapter_issues(chapter_id: int, session: Session = Depends(get_session)):
    statement = select(Issue).where(Issue.chapter_id == chapter_id)
    return session.exec(statement).all()


@router.get("/chapters/{chapter_id}/issues/stats")
def get_chapter_issue_stats(chapter_id: int, session: Session = Depends(get_session)):
    """Return aggregate counts for the chapter's issues by status, type, and confidence band."""
    issues = session.exec(select(Issue).where(Issue.chapter_id == chapter_id)).all()

    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    high = medium = low = 0

    for issue in issues:
        status_counts[issue.status] = status_counts.get(issue.status, 0) + 1
        type_counts[issue.type] = type_counts.get(issue.type, 0) + 1
        if issue.confidence >= CONFIDENCE_HIGH_THRESHOLD:
            high += 1
        elif issue.confidence >= CONFIDENCE_MEDIUM_THRESHOLD:
            medium += 1
        else:
            low += 1

    reviewed = status_counts.get("approved", 0) + status_counts.get("rejected", 0)
    return {
        "total": len(issues),
        "reviewed": reviewed,
        "by_status": status_counts,
        "by_type": type_counts,
        "by_confidence": {"high": high, "medium": medium, "low": low},
    }


@router.post("/issues/batch-update")
def batch_update_issues(payload: IssueBatchUpdate, session: Session = Depends(get_session)):
    """Update status and/or note on multiple issues in a single request."""
    # SQLModel's Column type stubs don't expose `.in_()` directly; the method exists at runtime via SQLAlchemy.
    issues = session.exec(select(Issue).where(Issue.id.in_(payload.issue_ids))).all()  # type: ignore[attr-defined]
    found_ids = {issue.id for issue in issues}
    missing = [i for i in payload.issue_ids if i not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Issues not found: {missing}")

    now = utc_now()
    for issue in issues:
        if payload.status is not None:
            issue.status = payload.status
        if payload.note is not None:
            issue.note = payload.note
        issue.updated_at = now
        session.add(issue)

    session.commit()
    for issue in issues:
        session.refresh(issue)
    return issues


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
