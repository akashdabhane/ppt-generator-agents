import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.v1.deps import get_db, get_owned_project, get_owned_document
from app.models.project import Project
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentResponse
from app.services.storage import storage_service
from app.workers.tasks import dispatch_document_ingestion
from app.rag.vector_store import vector_store
from app.document_processing.detector import DocumentTypeDetector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])


@router.post("/projects/{project_id}/documents", response_model=DocumentResponse)
async def upload_document(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db)
):
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

    # 3. Trigger ingestion task via Celery worker (with fallback)
    dispatch_document_ingestion(doc.id, background_tasks)

    return doc


@router.get("/projects/{project_id}/documents", response_model=List[DocumentResponse])
def list_documents(
    project_id: str,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db)
):
    result = db.execute(select(Document).where(Document.project_id == project_id))
    return result.scalars().all()


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    doc: Document = Depends(get_owned_document),
    db: Session = Depends(get_db)
):
    # Remove the vectors too, otherwise new decks keep retrieving and citing the deleted document
    try:
        vector_store.delete_document_chunks(doc.project_id, doc.id, [c.vector_id for c in doc.chunks if c.vector_id])
    except Exception as e:
        logger.error(f"Failed to delete vectors for document {doc.id}: {e}")
    storage_service.delete_file(doc.storage_path)
    db.delete(doc)
    db.commit()
    return None


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    doc: Document = Depends(get_owned_document),
    db: Session = Depends(get_db)
):
    doc.status = DocumentStatus.UPLOADED
    doc.error_message = None
    db.commit()

    dispatch_document_ingestion(doc.id, background_tasks)
    return doc

