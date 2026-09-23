from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.models.presentation import PresentationStatus
from app.models.job import JobStatus


class PresentationGenerateRequest(BaseModel):
    prompt: str
    num_slides: int = 10
    audience: Optional[str] = "General"
    theme: str = "Professional"
    tone: Optional[str] = "Professional & Informative"
    language: str = "English"


class SlideResponse(BaseModel):
    id: str
    slide_number: int
    slide_type: str
    content_json: Dict[str, Any]
    citations_json: List[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class SlideRegenerateRequest(BaseModel):
    instructions: Optional[str] = None


class PresentationResponse(BaseModel):
    id: str
    project_id: str
    title: str
    prompt: str
    theme: str
    audience: Optional[str] = None
    tone: Optional[str] = None
    language: Optional[str] = None
    status: PresentationStatus
    pptx_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    slides: List[SlideResponse] = []
    # Fact-check result of the latest completed generation, e.g. "8/8 content slides cited · 1 unsupported claim(s) removed"
    generation_summary: Optional[str] = None

    class Config:
        from_attributes = True


class GenerationProgressResponse(BaseModel):
    job_id: str
    presentation_id: str
    status: JobStatus
    progress: int
    current_step: str
    error_message: Optional[str] = None
