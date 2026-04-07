from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer
from sqlmodel import Session, col, func, select

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
    """Return aggregate counts for the chapter's issues by status, type, confidence band, and review state."""
    # Count by legacy status using a single GROUP BY query — avoids loading full Issue rows.
    status_rows = session.exec(
        select(Issue.status, func.count()).where(Issue.chapter_id == chapter_id).group_by(Issue.status)
    ).all()
    status_counts = {status: count for status, count in status_rows}

    # Count by type using a single GROUP BY query.
    type_rows = session.exec(
        select(Issue.type, func.count()).where(Issue.chapter_id == chapter_id).group_by(Issue.type)
    ).all()
    type_counts = {issue_type: count for issue_type, count in type_rows}

    # Count confidence bands using conditional aggregation.
    high, medium, low = session.exec(
        select(
            func.sum(func.cast(col(Issue.confidence) >= CONFIDENCE_HIGH_THRESHOLD, Integer)),
            func.sum(
                func.cast(
                    (col(Issue.confidence) >= CONFIDENCE_MEDIUM_THRESHOLD) & (col(Issue.confidence) < CONFIDENCE_HIGH_THRESHOLD),
                    Integer,
                )
            ),
            func.sum(func.cast(col(Issue.confidence) < CONFIDENCE_MEDIUM_THRESHOLD, Integer)),
        ).where(Issue.chapter_id == chapter_id)
    ).one()

    # Count by new review_state field
    review_state_rows = session.exec(
        select(Issue.review_state, func.count()).where(Issue.chapter_id == chapter_id).group_by(Issue.review_state)
    ).all()
    review_state_counts = {state: count for state, count in review_state_rows}

    # Count by editor_decision
    decision_rows = session.exec(
        select(Issue.editor_decision, func.count()).where(Issue.chapter_id == chapter_id).group_by(Issue.editor_decision)
    ).all()
    decision_counts = {decision if decision else "none": count for decision, count in decision_rows}

    # Count by model_action
    action_rows = session.exec(
        select(Issue.model_action, func.count()).where(Issue.chapter_id == chapter_id).group_by(Issue.model_action)
    ).all()
    action_counts = {action if action else "none": count for action, count in action_rows}

    total = sum(status_counts.values())
    # Use new review_state for reviewed count, fallback to legacy status
    reviewed = review_state_counts.get("reviewed", 0)
    # If no issues have the new review_state yet, fall back to legacy calculation
    if reviewed == 0 and total > 0:
        reviewed = status_counts.get("approved", 0) + status_counts.get("rejected", 0)

    return {
        "total": total,
        "reviewed": reviewed,
        "by_status": status_counts,
        "by_type": type_counts,
        "by_confidence": {"high": int(high or 0), "medium": int(medium or 0), "low": int(low or 0)},
        # New v2 fields
        "by_review_state": review_state_counts,
        "by_editor_decision": decision_counts,
        "by_model_action": action_counts,
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
        # Legacy status field (deprecated)
        if payload.status is not None:
            issue.status = payload.status
        # New v2 decision fields
        if payload.editor_decision is not None:
            issue.editor_decision = payload.editor_decision
            # When editor makes a decision, mark as reviewed
            issue.review_state = "reviewed"
        if payload.review_state is not None:
            issue.review_state = payload.review_state
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

    # Legacy status field (deprecated)
    if payload.status is not None:
        issue.status = payload.status
    # New v2 decision fields
    if payload.editor_decision is not None:
        issue.editor_decision = payload.editor_decision
        # When editor makes a decision, mark as reviewed
        issue.review_state = "reviewed"
    if payload.review_state is not None:
        issue.review_state = payload.review_state
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
