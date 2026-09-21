from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.v1.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentResponse
from app.services.storage import storage_service
from app.workers.tasks import run_document_ingestion
from app.document_processing.detector import DocumentTypeDetector

router = APIRouter(tags=["Documents"])


@router.post("/projects/{project_id}/documents", response_model=DocumentResponse)
async def upload_document(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        doc_type = DocumentTypeDetector.detect_type(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_bytes = await file.read()
    file_size = len(file_bytes)
    await file.seek(0)

    # 1. Create document record
    doc = Document(
        project_id=project.id,
        filename=file.filename,
        file_type=doc_type,
        file_size=file_size,
        storage_path="",
        status=DocumentStatus.UPLOADED
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 2. Save physical file to storage
    saved_path = storage_service.save_document(project.id, doc.id, file.filename, file.file)
    doc.storage_path = saved_path
    db.commit()

    # 3. Trigger ingestion background task
    background_tasks.add_task(run_document_ingestion, doc.id)

    return doc


@router.get("/projects/{project_id}/documents", response_model=List[DocumentResponse])
def list_documents(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    result = db.execute(select(Document).where(Document.project_id == project_id))
    return result.scalars().all()


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    project = db.get(Project, doc.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    storage_service.delete_file(doc.storage_path)
    db.delete(doc)
    db.commit()
    return None


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = DocumentStatus.UPLOADED
    doc.error_message = None
    db.commit()

    background_tasks.add_task(run_document_ingestion, doc.id)
    return doc
