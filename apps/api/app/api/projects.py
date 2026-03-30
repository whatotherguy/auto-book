from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, delete, select

from ..db import get_session
from ..models import AnalysisJob, Chapter, Issue, Project
from ..schemas import ProjectCreate
from ..services.storage import delete_project_dirs

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
    return session.exec(select(Project)).all()


@router.get("/{project_id}")
def get_project(project_id: int, session: Session = Depends(get_session)):
    return session.get(Project, project_id)


@router.delete("/{project_id}")
def delete_project(project_id: int, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    chapter_ids = session.exec(select(Chapter.id).where(Chapter.project_id == project_id)).all()

    if chapter_ids:
        session.exec(delete(Issue).where(Issue.chapter_id.in_(chapter_ids)))
        session.exec(delete(AnalysisJob).where(AnalysisJob.chapter_id.in_(chapter_ids)))
        session.exec(delete(Chapter).where(Chapter.project_id == project_id))

    session.delete(project)
    session.commit()

    delete_project_dirs(project_id)

    return {"ok": True, "deleted_project_id": project_id}
