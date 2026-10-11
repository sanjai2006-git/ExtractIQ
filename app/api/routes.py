import datetime
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.extraction.llm_extractor import ExtractionError
from app.models import Document, Extraction, ExtractionStatus
from app.pipeline import run_pipeline
from app.schemas import DocumentDetailOut, DocumentOut, ExtractionOut, ReviewDecision

router = APIRouter()


@router.post("/documents/upload", response_model=DocumentDetailOut)
def upload_document(file: UploadFile, db: Session = Depends(get_db)):
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF uploads are supported in this starter.")

    dest_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = settings.STORAGE_DIR / dest_name
    with open(dest_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    document = Document(filename=file.filename, filepath=str(dest_path))
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        run_pipeline(document, db)
    except ExtractionError as e:
        raise HTTPException(422, f"Extraction failed: {e}") from e

    db.refresh(document)
    return document


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(Document).order_by(Document.uploaded_at.desc()).all()


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found.")
    return document


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found.")
    return FileResponse(document.filepath, media_type="application/pdf")


@router.get("/review/queue", response_model=list[ExtractionOut])
def get_review_queue(db: Session = Depends(get_db)):
    return (
        db.query(Extraction)
        .filter(Extraction.status == ExtractionStatus.PENDING_REVIEW)
        .order_by(Extraction.overall_confidence.asc())
        .all()
    )


@router.post("/review/{extraction_id}/decision", response_model=ExtractionOut)
def submit_review_decision(
    extraction_id: int, decision: ReviewDecision, db: Session = Depends(get_db)
):
    extraction = db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(404, "Extraction not found.")

    if decision.decision == "approve":
        extraction.status = ExtractionStatus.APPROVED
    elif decision.decision == "reject":
        extraction.status = ExtractionStatus.REJECTED
    elif decision.decision == "correct":
        if decision.corrected_data is None:
            raise HTTPException(400, "corrected_data is required for a 'correct' decision.")
        extraction.corrected_data = decision.corrected_data
        extraction.status = ExtractionStatus.CORRECTED
    else:
        raise HTTPException(400, "decision must be 'approve', 'reject', or 'correct'.")

    extraction.reviewed_by = decision.reviewer
    extraction.review_notes = decision.notes
    extraction.reviewed_at = datetime.datetime.now(datetime.timezone.utc)

    db.commit()
    db.refresh(extraction)
    return extraction
