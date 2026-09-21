import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.v1.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
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
from app.workers.tasks import run_presentation_generation
from app.rag.graph import rag_engine

router = APIRouter(tags=["Presentations"])


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

    # 3. Trigger background generation task
    background_tasks.add_task(run_presentation_generation, job.id)

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
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    project = db.get(Project, pres.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")

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
    result = db.execute(
        select(GenerationJob)
        .where(GenerationJob.presentation_id == presentation_id)
        .order_by(GenerationJob.started_at.desc())
    )
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
    if not pres or not pres.pptx_path or not os.path.exists(pres.pptx_path):
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
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    result = db.execute(
        select(PresentationSlide)
        .where(PresentationSlide.presentation_id == presentation_id)
        .where(PresentationSlide.slide_number == slide_number)
    )
    slide = result.scalars().first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    # Update slide content using LLM context
    new_spec = rag_engine.execute(
        project_id=pres.project_id,
        prompt=req.instructions or f"Regenerate slide {slide_number} for {pres.prompt}",
        num_slides=1,
        theme=pres.theme
    )
    if new_spec.slides:
        first_slide_dict = new_spec.slides[0].model_dump() if hasattr(new_spec.slides[0], "model_dump") else new_spec.slides[0]
        slide.content_json = first_slide_dict
        slide.slide_type = first_slide_dict.get("type", slide.slide_type)
        slide.citations_json = first_slide_dict.get("citations", slide.citations_json)
        db.commit()

    return SlideResponse.model_validate(slide)


@router.delete("/presentations/{presentation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_presentation(
    presentation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pres = db.get(Presentation, presentation_id)
    if not pres:
        raise HTTPException(status_code=404, detail="Presentation not found")

    db.delete(pres)
    db.commit()
    return None
