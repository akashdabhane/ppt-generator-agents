import os
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.api.v1.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.document import Document, DocumentStatus
from app.models.presentation import Presentation, PresentationStatus
from app.models.slide import PresentationSlide
from app.models.job import GenerationJob, JobStatus
from app.schemas.presentation import (
    PresentationGenerateRequest,
    PresentationResponse,
    GenerationProgressResponse,
    SlideRegenerateRequest,
    SlideResponse
)
from app.workers.tasks import dispatch_presentation_generation
from app.services.storage import storage_service
from app.rag.graph import rag_engine, NoGroundingContextError, SlideRegenerationUnavailable
from app.presentation.renderer import PresentationRenderer
from app.schemas.presentation_spec import PresentationSpec

router = APIRouter(tags=["Presentations"])

STALE_JOB_TIMEOUT = timedelta(minutes=10)


@router.post("/projects/{project_id}/presentations/generate", response_model=GenerationProgressResponse)
def generate_presentation(
    project_id: str,
    req: PresentationGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Grounding: without indexed documents the deck could only be invented
    indexed = db.execute(
        select(func.count(Document.id))
        .where(Document.project_id == project.id)
        .where(Document.status == DocumentStatus.INDEXED)
    ).scalar() or 0
    if indexed == 0:
        raise HTTPException(
            status_code=400,
            detail="Upload at least one document and wait until it is INDEXED before generating a presentation."
        )

    # 1. Create presentation record
    pres = Presentation(
        project_id=project.id,
        title=req.prompt[:50].title(),
        prompt=req.prompt,
        theme=req.theme,
        status=PresentationStatus.PENDING
    )
    db.add(pres)
    db.commit()
    db.refresh(pres)

    # 2. Create GenerationJob
    job = GenerationJob(
        presentation_id=pres.id,
        status=JobStatus.QUEUED,
        progress=0,
        current_step_description="Job queued"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 3. Trigger generation task via Celery worker (with fallback)
    dispatch_presentation_generation(
        job.id,
        background_tasks,
        num_slides=req.num_slides,
        audience=req.audience or "General",
    )

    return GenerationProgressResponse(
        job_id=job.id,
        presentation_id=pres.id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step_description
    )



@router.get("/projects/{project_id}/presentations", response_model=List[PresentationResponse])
def list_presentations(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    result = db.execute(
        select(Presentation)
        .where(Presentation.project_id == project_id)
        .order_by(Presentation.created_at.desc())
    )
    presentations = result.scalars().all()
    
    res = []
    for p in presentations:
        slides_res = db.execute(
            select(PresentationSlide)
            .where(PresentationSlide.presentation_id == p.id)
            .order_by(PresentationSlide.slide_number)
        )
        slides = slides_res.scalars().all()
        
        p_dict = PresentationResponse.model_validate(p)
        p_dict.slides = [SlideResponse.model_validate(s) for s in slides]
        res.append(p_dict)
    return res


@router.get("/presentations/{presentation_id}", response_model=PresentationResponse)
def get_presentation(
    presentation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pres = db.get(Presentation, presentation_id)
    project = db.get(Project, pres.project_id) if pres else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")

    slides_res = db.execute(
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == pres.id)
        .order_by(PresentationSlide.slide_number)
    )
    slides = slides_res.scalars().all()

    p_dict = PresentationResponse.model_validate(pres)
    p_dict.slides = [SlideResponse.model_validate(s) for s in slides]
    return p_dict


@router.get("/presentations/{presentation_id}/progress")
def get_presentation_progress(
    presentation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pres = db.get(Presentation, presentation_id)
    project = db.get(Project, pres.project_id) if pres else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")

    result = db.execute(
        select(GenerationJob)
        .where(GenerationJob.presentation_id == presentation_id)
        .order_by(GenerationJob.started_at.desc())
    )
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # A job whose worker process died (e.g. server restart) never reaches a final state
    if (
        job.status not in (JobStatus.COMPLETED, JobStatus.FAILED)
        and datetime.utcnow() - job.started_at > STALE_JOB_TIMEOUT
    ):
        job.status = JobStatus.FAILED
        job.error_message = "Generation timed out or the worker stopped. Please try again."
        job.current_step_description = job.error_message
        pres.status = PresentationStatus.FAILED
        db.commit()

    return GenerationProgressResponse(
        job_id=job.id,
        presentation_id=presentation_id,
        status=job.status,
        progress=job.progress,
        current_step=job.current_step_description,
        error_message=job.error_message
    )


@router.get("/presentations/{presentation_id}/download")
def download_presentation(
    presentation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pres = db.get(Presentation, presentation_id)
    project = db.get(Project, pres.project_id) if pres else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")
    if not pres.pptx_path or not os.path.exists(pres.pptx_path):
        raise HTTPException(status_code=404, detail="PPTX file not found or generation incomplete")

    filename = f"{pres.title.replace(' ', '_')}.pptx"
    return FileResponse(
        path=pres.pptx_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename
    )


@router.post("/presentations/{presentation_id}/slides/{slide_number}/regenerate", response_model=SlideResponse)
def regenerate_single_slide(
    presentation_id: str,
    slide_number: int,
    req: SlideRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pres = db.get(Presentation, presentation_id)
    project = db.get(Project, pres.project_id) if pres else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")
    if pres.status != PresentationStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Only a completed presentation can have slides regenerated.")

    slides = db.execute(
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .order_by(PresentationSlide.slide_number)
    ).scalars().all()
    slide = next((s for s in slides if s.slide_number == slide_number), None)
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    try:
        new_slide = rag_engine.regenerate_slide(
            project_id=pres.project_id,
            deck_prompt=pres.prompt,
            current=slide.content_json,
            instructions=req.instructions,
        )
    except (NoGroundingContextError, SlideRegenerationUnavailable) as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_dict = new_slide.model_dump()
    slide.content_json = new_dict
    slide.slide_type = new_dict["type"]
    slide.citations_json = new_dict.get("citations", [])

    # Re-render the .pptx so the download matches the preview
    spec = PresentationSpec(title=pres.title, slides=[s.content_json for s in slides])
    output_path = pres.pptx_path or storage_service.get_presentation_path(pres.project_id, pres.id)
    PresentationRenderer(theme_name=pres.theme).render(spec, output_path)
    pres.pptx_path = output_path
    db.commit()
    db.refresh(slide)

    return SlideResponse.model_validate(slide)


@router.delete("/presentations/{presentation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_presentation(
    presentation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pres = db.get(Presentation, presentation_id)
    project = db.get(Project, pres.project_id) if pres else None
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Presentation not found")

    # The worker writes to this row and the .pptx while generating; a stale job may be deleted.
    if (
        pres.status in (PresentationStatus.PENDING, PresentationStatus.GENERATING)
        and datetime.utcnow() - pres.created_at < STALE_JOB_TIMEOUT
    ):
        raise HTTPException(status_code=409, detail="This presentation is still generating. Try again once it finishes.")

    pptx_path = pres.pptx_path
    db.delete(pres)
    db.commit()
    if pptx_path:
        storage_service.delete_file(pptx_path)
    return None
