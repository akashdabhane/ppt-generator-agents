import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


class PresentationStatus(str, Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Presentation(Base):
    __tablename__ = "presentations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    theme: Mapped[str] = mapped_column(String(50), default="Professional", nullable=False)
    # Generation settings, reused when a single slide is regenerated (migration 0002)
    audience: Mapped[str] = mapped_column(String(100), nullable=True)
    tone: Mapped[str] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[PresentationStatus] = mapped_column(SQLEnum(PresentationStatus), default=PresentationStatus.PENDING, nullable=False)
    pptx_path: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="presentations")
    slides = relationship("PresentationSlide", back_populates="presentation", cascade="all, delete-orphan", order_by="PresentationSlide.slide_number")
    jobs = relationship("GenerationJob", back_populates="presentation", cascade="all, delete-orphan")
