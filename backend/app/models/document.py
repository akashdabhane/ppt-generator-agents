import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(SQLEnum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
