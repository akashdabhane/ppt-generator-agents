import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


class PresentationSlide(Base):
    __tablename__ = "presentation_slides"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    presentation_id: Mapped[str] = mapped_column(String, ForeignKey("presentations.id", ondelete="CASCADE"), nullable=False, index=True)
    slide_number: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    citations_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    presentation = relationship("Presentation", back_populates="slides")
