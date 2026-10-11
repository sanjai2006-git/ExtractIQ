# Document Extraction Pipeline

OCR + LLM extraction over messy PDFs, tables, and scanned documents — with a
validation layer and a human review queue for anything the pipeline isn't
confident about.

This starter ships with **invoices** as the example document type. The
extraction schema is swappable — see "Adding a new document type" below.

## Why it's built this way

Raw OCR gives you text, not meaning. Raw LLM extraction on a blurry scan can
confidently hallucinate. Neither is safe to run unattended on real business
documents. So the pipeline is deliberately four layers, not one:

```
                 ┌──────────────┐
  PDF / scan ──► │  1. Parse    │  text layer if present, else OCR
                 │  (OCR)       │  → per-page confidence
                 └──────┬───────┘
                        ▼
                 ┌──────────────┐
                 │ 2. Extract   │  Claude, structured tool-use output,
                 │  (LLM)       │  per-field confidence baked into schema
                 └──────┬───────┘
                        ▼
                 ┌──────────────┐
                 │ 3. Validate  │  schema checks + business rules
                 │              │  (totals reconcile, required fields,
                 │              │   OCR + field confidence thresholds)
                 └──────┬───────┘
                   pass │ fail/low-confidence
              ┌─────────┴─────────┐
              ▼                   ▼
      auto-approved        ┌──────────────┐
      → saved               │ 4. Review    │  human corrects/approves
                             │  queue       │  via the dashboard
                             └──────────────┘
```

Nothing reaches "approved" data without either clearing validation
automatically or being signed off by a human. That's the whole point of the
project — reliability, not just extraction.

## Stack

- **FastAPI** — API + serves the review dashboard
- **PyMuPDF** — text-layer extraction (fast path, no OCR needed for
  text-native PDFs)
- **Tesseract (pytesseract + pdf2image)** — OCR fallback for scanned pages.
  Swap for AWS Textract / Azure Document Intelligence for production-grade
  accuracy on messy scans (see `app/ocr/parser.py`)
- **Anthropic Claude** (structured tool-use) — extraction into a typed schema
- **Pydantic** — the extraction schema doubles as the validation contract
- **SQLAlchemy + SQLite** — storage (swap `DATABASE_URL` for Postgres in
  production)
- **Vanilla HTML/JS dashboard** — the human review queue

## Setup

```bash
cd extraction-pipeline
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# System dependencies for OCR fallback:
#   macOS:  brew install tesseract poppler
#   Ubuntu: sudo apt-get install tesseract-ocr poppler-utils

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

uvicorn app.main:app --reload
```

Open `http://localhost:8000` for the review dashboard.
API docs at `http://localhost:8000/docs`.

## Using it

```bash
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample_invoice.pdf"
```

The pipeline runs synchronously on upload for this starter (simple to run
and debug). Anything below the confidence threshold lands in
`GET /review/queue` instead of being auto-approved.

## Adding a new document type

1. Define a new Pydantic model in `app/schemas.py` (see `InvoiceExtraction`
   for the pattern — every field gets a sibling `<field>_confidence` in the
   response via the tool schema).
2. Add matching business rules in `app/validation/validator.py`.
3. Pass the new schema into `extract()` in `app/extraction/llm_extractor.py`
   at call time (it's schema-driven, not hardcoded to invoices).

## Taking this to production

This starter optimizes for being easy to read end-to-end. Before real load:

- **Async processing**: move the pipeline call in `app/api/routes.py` onto a
  Celery/RQ task queue instead of running inline on the upload request.
- **Managed OCR**: swap Tesseract for AWS Textract or Azure Document
  Intelligence — both handle skewed scans, handwriting, and tables far more
  reliably, and return real per-word confidence instead of Tesseract's
  noisier estimate.
- **Postgres**, not SQLite, once more than one worker writes at a time.
- **Object storage** (S3-compatible) for source documents instead of local
  disk (`app/config.py` → `STORAGE_DIR`).
- **Auth** on the review dashboard and API — there is none in this starter.
