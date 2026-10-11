import datetime
import enum

from sqlalchemy import JSON, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ExtractionStatus(str, enum.Enum):
    AUTO_APPROVED = "auto_approved"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    doc_type = Column(String, default="invoice")
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)
    ocr_confidence = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    extraction = relationship(
        "Extraction", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)

    # Raw LLM output, validated against the Pydantic schema for doc_type
    data = Column(JSON, nullable=False)
    # Per-field confidence (0-1) as reported by the LLM at extraction time
    field_confidences = Column(JSON, nullable=True)
    # Human-corrected version, if any — kept separate from `data` so the
    # original model output is always preserved for auditing/eval
    corrected_data = Column(JSON, nullable=True)

    overall_confidence = Column(Float, nullable=False)
    validation_flags = Column(JSON, default=list)  # list[str] of failed checks

    status = Column(Enum(ExtractionStatus), default=ExtractionStatus.PENDING_REVIEW)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    document = relationship("Document", back_populates="extraction")
