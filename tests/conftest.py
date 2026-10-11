"""
Sets test-only environment variables before any `app.*` module is imported
anywhere in the test session — `app/config.py` reads these at import time,
so this has to run first. Using a throwaway SQLite file keeps tests from
touching the real extraction.db used in development.
"""

import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp_db.name}")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used-llm-is-mocked")

import fitz  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture
def sample_invoice_pdf(tmp_path):
    """A real text-layer PDF (no OCR needed) matching the values asserted
    against in test_pipeline.py."""
    path = tmp_path / "sample_invoice.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Acme Supplies Inc.\n"
        "Invoice #INV-2026-0042\n"
        "Date: 2026-09-01\n"
        "Due: 2026-09-30\n\n"
        "Widget A   2   50.00   100.00\n\n"
        "Subtotal: 100.00\nTax: 8.00\nTotal: 108.00",
    )
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
