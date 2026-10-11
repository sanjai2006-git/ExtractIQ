"""
Wires the four layers together for a single document. Kept as one plain
function, run synchronously on upload in this starter, so the whole flow is
readable in one place. For real throughput, call `run_pipeline` from a
Celery/RQ task instead of inline in the upload request handler.
"""

from sqlalchemy.orm import Session

from app.extraction.llm_extractor import ExtractionError, extract
from app.models import Document, DocumentStatus, Extraction, ExtractionStatus
from app.ocr.parser import parse_document
from app.schemas import InvoiceExtraction
from app.validation.validator import validate_invoice


def run_pipeline(document: Document, db: Session) -> Extraction:
    document.status = DocumentStatus.PROCESSING
    db.commit()

    try:
        # 1. Parse (text layer, OCR fallback per page)
        parsed = parse_document(document.filepath)
        print("\n========== PARSED PDF TEXT ==========")
        print(f"Text length: {len(parsed.full_text)}")
        print(parsed.full_text[:5000])
        print("========== END PDF TEXT ==========\n")

        document.ocr_confidence = parsed.overall_confidence

        # 2. Extract (LLM, structured tool-use)
        extraction_data: InvoiceExtraction = extract(
            document_text=parsed.full_text,
            schema=InvoiceExtraction,
            doc_type_label="invoice",
        )

        # 3. Validate (business rules + confidence)
        result = validate_invoice(extraction_data, ocr_confidence=parsed.overall_confidence)

        status = (
            ExtractionStatus.PENDING_REVIEW if result.needs_review else ExtractionStatus.AUTO_APPROVED
        )

        extraction_record = Extraction(
            document_id=document.id,
            data=extraction_data.model_dump(exclude={"field_confidences"}),
            field_confidences=extraction_data.field_confidences,
            overall_confidence=result.overall_confidence,
            validation_flags=result.flags,
            status=status,
        )
        db.add(extraction_record)

        document.status = DocumentStatus.PROCESSED
        db.commit()
        db.refresh(extraction_record)
        return extraction_record

    except ExtractionError as e:
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)
        db.commit()
        raise
