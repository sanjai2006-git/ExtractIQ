from app.ocr.parser import parse_document


def test_text_layer_pdf_skips_ocr(sample_invoice_pdf):
    parsed = parse_document(str(sample_invoice_pdf))

    assert len(parsed.pages) == 1
    assert parsed.pages[0].source == "text_layer"
    # text-layer pages are treated as fully confident (no OCR uncertainty)
    assert parsed.overall_confidence == 1.0
    assert "Acme Supplies Inc." in parsed.pages[0].text
    assert "INV-2026-0042" in parsed.pages[0].text
