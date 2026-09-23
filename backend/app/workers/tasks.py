import logging
from datetime import datetime
from typing import Optional
from fastapi import BackgroundTasks
from sqlalchemy import select
from app.core.config import settings
from app.workers.celery_app import celery_app
from app.database.session import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.chunk import DocumentChunk
from app.models.presentation import Presentation, PresentationStatus
from app.models.slide import PresentationSlide
from app.models.job import GenerationJob, JobStatus
from app.document_processing.chunker import DocumentChunker
from app.rag.vector_store import vector_store
from app.rag.graph import rag_engine
from app.presentation.renderer import PresentationRenderer
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


def run_document_ingestion(document_id: str):
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if not doc:
            return

        try:
            doc.status = DocumentStatus.PROCESSING
            db.commit()

            # Chunk document
            chunker = DocumentChunker()
            doc.status = DocumentStatus.CHUNKING
            db.commit()

            chunks_data = chunker.process_and_chunk(doc.id, doc.filename, doc.storage_path)

            # Store in DB & Vector Store
            doc.status = DocumentStatus.EMBEDDING
            db.commit()

            # Idempotent: a reindex/retry replaces this document's previous chunks instead of duplicating them
            old_chunks = db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc.id)).scalars().all()
            vector_store.delete_document_chunks(doc.project_id, doc.id, [c.vector_id for c in old_chunks if c.vector_id])
            for old in old_chunks:
                db.delete(old)
            db.flush()

            vector_ids = vector_store.upsert_chunks(doc.project_id, chunks_data)

            for idx, c in enumerate(chunks_data):
                v_id = vector_ids[idx] if idx < len(vector_ids) else None
                chunk_obj = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=c["chunk_index"],
                    content=c["content"],
                    page_number=c.get("page"),
                    section=c.get("section"),
                    metadata_json=c["metadata"],
                    vector_id=v_id
                )
                db.add(chunk_obj)

            doc.status = DocumentStatus.INDEXED
            db.commit()
        except Exception as e:
            doc.status = DocumentStatus.FAILED
            doc.error_message = str(e)
            db.commit()


def run_presentation_generation(job_id: str, num_slides: int = 10, audience: str = "General",
                                tone: str = "Professional & Informative", language: str = "English"):
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        if not job:
            return

        pres = db.get(Presentation, job.presentation_id)
        if not pres:
            return

        def on_progress(stage: str, percent: int, message: str):
            job.status = JobStatus[stage]
            job.progress = percent
            job.current_step_description = message
            db.commit()

        try:
            pres.status = PresentationStatus.GENERATING
            on_progress("RETRIEVING_DOCUMENTS", 5, "Starting generation")

            # Steps 1-2: plan + retrieve, write, fact-check and repair (see rag/graph.py)
            # Settings saved on the presentation win over task arguments (older queued jobs have none saved)
            spec, report = rag_engine.execute_with_report(
                project_id=pres.project_id,
                prompt=pres.prompt,
                num_slides=num_slides,
                audience=pres.audience or audience,
                theme=pres.theme,
                tone=pres.tone or tone,
                language=pres.language or language,
                on_progress=on_progress,
            )

            # Step 3: Rendering Presentation
            on_progress("RENDERING_PRESENTATION", 80, f"Rendering slides ({report.summary()})")

            output_pptx_path = storage_service.get_presentation_path(pres.project_id, pres.id)
            renderer = PresentationRenderer(theme_name=pres.theme)
            renderer.render(spec, output_pptx_path)

            # Save generated slides into database
            for slide_idx, s_spec in enumerate(spec.slides, start=1):
                s_dict = s_spec.model_dump() if hasattr(s_spec, "model_dump") else s_spec
                slide_obj = PresentationSlide(
                    presentation_id=pres.id,
                    slide_number=slide_idx,
                    slide_type=s_dict.get("type", "bullet"),
                    content_json=s_dict,
                    citations_json=s_dict.get("citations", [])
                )
                db.add(slide_obj)

            # Step 4: Complete. The grounding summary stays on the job for troubleshooting
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.current_step_description = f"Complete: {report.summary()}"
            job.completed_at = datetime.utcnow()

            pres.status = PresentationStatus.COMPLETED
            pres.pptx_path = output_pptx_path
            pres.title = spec.title or pres.title
            db.commit()

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.current_step_description = f"Generation failed: {str(e)}"
            pres.status = PresentationStatus.FAILED
            db.commit()


def _broker_available() -> bool:
    """Quick Redis ping so dispatch falls back immediately instead of waiting on Celery's long reconnect retries."""
    try:
        import redis
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


@celery_app.task(name="tasks.process_document")
def process_document_task(document_id: str):
    run_document_ingestion(document_id)


@celery_app.task(name="tasks.generate_presentation")
def generate_presentation_task(job_id: str, num_slides: int = 10, audience: str = "General",
                               tone: str = "Professional & Informative", language: str = "English"):
    run_presentation_generation(job_id, num_slides, audience, tone, language)


def dispatch_document_ingestion(document_id: str, background_tasks: Optional[BackgroundTasks] = None):
    """Dispatch document ingestion task to Celery worker, with fallback to FastAPI background tasks."""
    try:
        if not _broker_available():
            raise ConnectionError(f"Redis broker not reachable at {settings.CELERY_BROKER_URL}")
        process_document_task.delay(document_id)
        logger.info(f"Dispatched document ingestion task {document_id} to Celery worker.")
    except Exception as e:
        logger.warning(f"Celery broker unavailable ({e}). Falling back to in-process execution.")
        if background_tasks:
            background_tasks.add_task(run_document_ingestion, document_id)
        else:
            run_document_ingestion(document_id)


def dispatch_presentation_generation(
    job_id: str,
    background_tasks: Optional[BackgroundTasks] = None,
    num_slides: int = 10,
    audience: str = "General",
    tone: str = "Professional & Informative",
    language: str = "English",
):
    """Dispatch presentation generation task to Celery worker, with fallback to FastAPI background tasks."""
    try:
        if not _broker_available():
            raise ConnectionError(f"Redis broker not reachable at {settings.CELERY_BROKER_URL}")
        generate_presentation_task.delay(job_id, num_slides, audience, tone, language)
        logger.info(f"Dispatched presentation generation task {job_id} to Celery worker.")
    except Exception as e:
        logger.warning(f"Celery broker unavailable ({e}). Falling back to in-process execution.")
        if background_tasks:
            background_tasks.add_task(run_presentation_generation, job_id, num_slides, audience, tone, language)
        else:
            run_presentation_generation(job_id, num_slides, audience, tone, language)

