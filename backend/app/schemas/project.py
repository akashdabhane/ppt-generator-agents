from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    presentation_count: int = 0

    class Config:
        from_attributes = True
