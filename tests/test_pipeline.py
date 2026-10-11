from unittest.mock import patch

from app.schemas import InvoiceExtraction, LineItem

LOW_CONFIDENCE_EXTRACTION = InvoiceExtraction(
    vendor_name="Acme Supplies Inc.",
    invoice_number="INV-2026-0042",
    invoice_date="2026-09-01",
    due_date="2026-09-30",
    line_items=[LineItem(description="Widget A", quantity=2, unit_price=50.0, amount=100.0)],
    subtotal=100.0,
    tax=8.0,
    total=108.0,
    currency="USD",
    # deliberately low so this extraction lands in the review queue
    field_confidences={"vendor_name": 0.5, "invoice_number": 0.6, "total": 0.55},
)

HIGH_CONFIDENCE_EXTRACTION = LOW_CONFIDENCE_EXTRACTION.model_copy(
    update={"field_confidences": {"vendor_name": 0.98, "invoice_number": 0.99, "total": 0.97}}
)


def _upload(client, sample_invoice_pdf):
    with open(sample_invoice_pdf, "rb") as f:
        return client.post(
            "/documents/upload",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")},
        )


def test_low_confidence_extraction_lands_in_review_queue(client, sample_invoice_pdf):
    with patch("app.pipeline.extract", return_value=LOW_CONFIDENCE_EXTRACTION):
        response = _upload(client, sample_invoice_pdf)

    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["status"] == "pending_review"

    queue = client.get("/review/queue").json()
    assert any(item["document_id"] == body["id"] for item in queue)


def test_high_confidence_extraction_auto_approves(client, sample_invoice_pdf):
    with patch("app.pipeline.extract", return_value=HIGH_CONFIDENCE_EXTRACTION):
        response = _upload(client, sample_invoice_pdf)

    assert response.status_code == 200
    assert response.json()["extraction"]["status"] == "auto_approved"


def test_review_decision_clears_item_from_queue(client, sample_invoice_pdf):
    with patch("app.pipeline.extract", return_value=LOW_CONFIDENCE_EXTRACTION):
        upload_response = _upload(client, sample_invoice_pdf)

    extraction_id = upload_response.json()["extraction"]["id"]
    queue_before = client.get("/review/queue").json()
    assert any(item["id"] == extraction_id for item in queue_before)

    decision_response = client.post(
        f"/review/{extraction_id}/decision",
        json={
            "decision": "correct",
            "corrected_data": {
                **LOW_CONFIDENCE_EXTRACTION.model_dump(exclude={"field_confidences"}),
                "total": 108.0,
            },
            "reviewer": "sanjay",
        },
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "corrected"

    queue_after = client.get("/review/queue").json()
    assert not any(item["id"] == extraction_id for item in queue_after)


def test_original_pdf_is_retrievable(client, sample_invoice_pdf):
    with patch("app.pipeline.extract", return_value=HIGH_CONFIDENCE_EXTRACTION):
        upload_response = _upload(client, sample_invoice_pdf)

    document_id = upload_response.json()["id"]
    file_response = client.get(f"/documents/{document_id}/file")

    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "application/pdf"
