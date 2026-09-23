import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.api.v1.deps import get_db, get_current_user, get_owned_project
from app.models.user import User
from app.models.project import Project
from app.models.document import Document
from app.models.presentation import Presentation
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.storage import storage_service
from app.rag.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


def _to_response(project: Project, db: Session) -> ProjectResponse:
    doc_cnt = db.execute(select(func.count(Document.id)).where(Document.project_id == project.id)).scalar() or 0
    pres_cnt = db.execute(select(func.count(Presentation.id)).where(Presentation.project_id == project.id)).scalar() or 0
    return ProjectResponse(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=doc_cnt,
        presentation_count=pres_cnt
    )


@router.post("", response_model=ProjectResponse)
def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = Project(
        user_id=current_user.id,
        name=project_in.name,
        description=project_in.description
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_response(project, db)


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    projects = db.execute(
        select(Project).where(Project.user_id == current_user.id).order_by(Project.created_at.desc())
    ).scalars().all()
    return [_to_response(p, db) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db)
):
    return _to_response(project, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    project_in: ProjectUpdate,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db)
):
    if project_in.name is not None:
        name = project_in.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Project name can't be empty")
        project.name = name
    if project_in.description is not None:
        project.description = project_in.description.strip() or None
    db.commit()
    db.refresh(project)
    return _to_response(project, db)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db)
):
    # Documents are private: remove their vectors and files too, not just the DB rows.
    # Vector cleanup is best-effort so an unreachable vector DB can't block the delete.
    try:
        vector_store.delete_project(project.id)
    except Exception as e:
        logger.error(f"Failed to delete vectors for project {project.id}: {e}")

    db.delete(project)
    db.commit()
    storage_service.delete_project_dir(project_id)
    return None
