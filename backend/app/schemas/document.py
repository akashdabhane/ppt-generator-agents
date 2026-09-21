from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
