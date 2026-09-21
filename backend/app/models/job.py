import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RETRIEVING_DOCUMENTS = "RETRIEVING_DOCUMENTS"
    GENERATING_OUTLINE = "GENERATING_OUTLINE"
    GENERATING_SLIDE_CONTENT = "GENERATING_SLIDE_CONTENT"
    RENDERING_PRESENTATION = "RENDERING_PRESENTATION"
    VALIDATING_SLIDES = "VALIDATING_SLIDES"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String, ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 to 100
    current_step_description: Mapped[str] = mapped_column(String(255), default="Queued", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    presentation = relationship("Presentation", back_populates="jobs")
