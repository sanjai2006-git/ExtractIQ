from app.schemas import InvoiceExtraction, LineItem
from app.validation.validator import validate_invoice


def _base_extraction(**overrides) -> InvoiceExtraction:
    defaults = dict(
        vendor_name="Acme Supplies Inc.",
        invoice_number="INV-2026-0042",
        invoice_date="2026-09-01",
        due_date="2026-09-30",
        line_items=[
            LineItem(description="Widget A", quantity=2, unit_price=50.0, amount=100.0),
            LineItem(description="Widget B", quantity=1, unit_price=30.0, amount=30.0),
        ],
        subtotal=130.0,
        tax=10.40,
        total=140.40,
        currency="USD",
        field_confidences={
            "vendor_name": 0.98,
            "invoice_number": 0.99,
            "total": 0.97,
            "subtotal": 0.95,
            "tax": 0.9,
        },
    )
    defaults.update(overrides)
    return InvoiceExtraction(**defaults)


def test_clean_extraction_auto_approves():
    result = validate_invoice(_base_extraction(), ocr_confidence=1.0)

    assert result.passed
    assert result.flags == []
    assert not result.needs_review


def test_total_mismatch_forces_review_regardless_of_confidence():
    extraction = _base_extraction(total=999.0)
    result = validate_invoice(extraction, ocr_confidence=1.0)

    assert not result.passed
    assert any("total_mismatch" in f for f in result.flags)
    assert result.needs_review
    # a failed business rule caps confidence even if fields were self-reported high
    assert result.overall_confidence <= 0.6


def test_line_items_not_summing_to_subtotal_is_flagged():
    extraction = _base_extraction(subtotal=500.0)
    result = validate_invoice(extraction, ocr_confidence=1.0)

    assert any("line_items_sum_mismatch" in f for f in result.flags)
    assert result.needs_review


def test_missing_required_fields_flagged():
    extraction = _base_extraction(invoice_number=None, total=None)
    result = validate_invoice(extraction, ocr_confidence=1.0)

    assert "missing_invoice_number" in result.flags
    assert "missing_total" in result.flags
    assert result.needs_review


def test_poor_ocr_quality_forces_review_even_with_no_flags():
    extraction = _base_extraction(
        field_confidences={k: 0.9 for k in _base_extraction().field_confidences}
    )
    result = validate_invoice(extraction, ocr_confidence=0.3)

    assert result.needs_review
    assert result.overall_confidence < 0.85


def test_low_field_confidence_is_flagged_individually():
    extraction = _base_extraction(field_confidences={"total": 0.4, "vendor_name": 0.95})
    result = validate_invoice(extraction, ocr_confidence=1.0)

    assert any("low_confidence_fields" in f and "total" in f for f in result.flags)
