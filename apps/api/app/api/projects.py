from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, delete, select

from ..db import get_session
from ..models import Chapter, Project
from ..schemas import ProjectCreate
from ..services.storage import delete_project_dirs
from .chapters import delete_chapter_dependent_records

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("")
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    project = Project(name=payload.name)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("")
def list_projects(session: Session = Depends(get_session)):
    projects = session.exec(select(Project)).all()

    # Build chapter counts in one query
    counts_q = (
        select(Chapter.project_id, func.count(Chapter.id))
        .group_by(Chapter.project_id)
    )
    counts = dict(session.exec(counts_q).all())

    return [
        {
            "id": p.id,
            "name": p.name,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "chapter_count": counts.get(p.id, 0),
        }
        for p in projects
    ]


@router.get("/{project_id}")
def get_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
def delete_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    chapter_ids = session.exec(select(Chapter.id).where(Chapter.project_id == project_id)).all()

    if chapter_ids:
        for chapter_id in chapter_ids:
            delete_chapter_dependent_records(session, chapter_id)
        session.exec(delete(Chapter).where(Chapter.project_id == project_id))

    session.delete(project)
    session.commit()

    delete_project_dirs(project_id)

    return {"ok": True, "deleted_project_id": project_id}
