import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.api.v1.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.document import Document
from app.models.presentation import Presentation
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.services.storage import storage_service
from app.rag.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


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
    return ProjectResponse(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
        document_count=0,
        presentation_count=0
    )


@router.get("", response_model=List[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = db.execute(select(Project).where(Project.user_id == current_user.id))
    projects = result.scalars().all()
    
    responses = []
    for p in projects:
        doc_cnt = db.execute(select(func.count(Document.id)).where(Document.project_id == p.id)).scalar() or 0
        pres_cnt = db.execute(select(func.count(Presentation.id)).where(Presentation.project_id == p.id)).scalar() or 0
        responses.append(ProjectResponse(
            id=p.id,
            user_id=p.user_id,
            name=p.name,
            description=p.description,
            created_at=p.created_at,
            updated_at=p.updated_at,
            document_count=doc_cnt,
            presentation_count=pres_cnt
        ))
    return responses


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

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


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Documents are private: remove their vectors and files too, not just the DB rows.
    # Vector cleanup is best-effort so an unreachable vector DB can't block the delete.
    for doc in project.documents:
        try:
            vector_store.delete_document_chunks(project.id, doc.id)
        except Exception as e:
            logger.error(f"Failed to delete vectors for document {doc.id}: {e}")

    db.delete(project)
    db.commit()
    storage_service.delete_project_dir(project_id)
    return None
