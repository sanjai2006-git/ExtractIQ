
"""
Parse PDFs using embedded text where available and OCR for scanned pages.
"""

from dataclasses import dataclass, field

import fitz
import pytesseract
from PIL import Image


# Pages with less text than this threshold will use OCR.
MIN_TEXT_LAYER_CHARS = 20

# Balance OCR speed and readability for invoices and bills.
OCR_DPI = 240


@dataclass
class ParsedPage:
    page_num: int
    text: str
    source: str
    confidence: float | None


@dataclass
class ParsedDocument:
    pages: list[ParsedPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(
            f"--- Page {p.page_num} ---\n{p.text}"
            for p in self.pages
        )

    @property
    def overall_confidence(self) -> float:
        if not self.pages:
            return 0.0

        scores = [
            p.confidence if p.confidence is not None else 1.0
            for p in self.pages
        ]
        return sum(scores) / len(scores)


def _ocr_page(page, page_index: int) -> ParsedPage:
    # Render the already-open PDF page directly using PyMuPDF.
    pix = page.get_pixmap(
        dpi=OCR_DPI,
        colorspace=fitz.csRGB,
        alpha=False,
    )

    image = Image.frombytes(
        "RGB",
        (pix.width, pix.height),
        pix.samples,
    )

    ocr_data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
    )

    words = []
    confidences = []

    for text, conf in zip(ocr_data["text"], ocr_data["conf"]):
        text = text.strip()

        if not text:
            continue

        words.append(text)

        try:
            conf_val = int(float(conf))
        except (ValueError, TypeError):
            conf_val = -1

        if conf_val >= 0:
            confidences.append(conf_val)

    avg_confidence = (
        sum(confidences) / len(confidences) / 100.0
        if confidences
        else 0.0
    )

    return ParsedPage(
        page_num=page_index + 1,
        text=" ".join(words),
        source="ocr",
        confidence=avg_confidence,
    )


def parse_document(pdf_path: str) -> ParsedDocument:
    parsed = ParsedDocument()

    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text_layer = page.get_text().strip()

            if len(text_layer) >= MIN_TEXT_LAYER_CHARS:
                parsed.pages.append(
                    ParsedPage(
                        page_num=i + 1,
                        text=text_layer,
                        source="text_layer",
                        confidence=None,
                    )
                )
            else:
                parsed.pages.append(_ocr_page(page, i))

    return parsed