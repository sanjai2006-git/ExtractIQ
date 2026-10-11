import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Extraction target schema. This doubles as:
#   1. the JSON schema handed to Claude as a tool definition
#   2. the validation contract the LLM's output must satisfy
#
# To add a new document type, define a sibling model here following the same
# shape (fields + a *_confidence field per meaningful field), then wire it
# into extraction/llm_extractor.py and validation/validator.py.
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class InvoiceExtraction(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO 8601 string; validated in validator.py
    due_date: Optional[str] = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: Optional[str] = None

    # Per-field confidence (0-1), as self-reported by the model. Keys match
    # the field names above. This is what lets the validator flag individual
    # fields for review instead of an entire document.
    field_confidences: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------


class DocumentOut(BaseModel):
    id: int
    filename: str
    doc_type: str
    status: str
    ocr_confidence: Optional[float]
    uploaded_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractionOut(BaseModel):
    id: int
    document_id: int
    data: dict
    field_confidences: Optional[dict]
    corrected_data: Optional[dict]
    overall_confidence: float
    validation_flags: list[str]
    status: str
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime.datetime]
    review_notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailOut(DocumentOut):
    extraction: Optional[ExtractionOut] = None


class ReviewDecision(BaseModel):
    decision: str  # "approve" | "reject" | "correct"
    corrected_data: Optional[dict] = None
    reviewer: Optional[str] = None
    notes: Optional[str] = None
