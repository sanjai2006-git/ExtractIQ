"""
The gate between "the model produced JSON" and "this data is trustworthy
enough to save without a human looking at it."

Two independent signals feed the decision:
  1. Confidence — OCR page confidence + the model's own per-field confidence.
  2. Business rules — concrete, checkable facts about the document
     (do the line items actually sum to the subtotal? is the date real?).

A low confidence score routes to review. But so does ANY failed business
rule, regardless of how confident the model claims to be — a totals
mismatch is a fact, not a probability, and it's exactly the kind of error
that's invisible if you only look at confidence scores.
"""

from dataclasses import dataclass, field
from datetime import date

from dateutil import parser as date_parser

from app.config import settings
from app.schemas import InvoiceExtraction

AMOUNT_TOLERANCE = 0.01  # absolute currency tolerance for reconciliation checks
FIELD_CONFIDENCE_FLOOR = 0.7  # per-field confidence below this gets flagged


@dataclass
class ValidationResult:
    passed: bool
    flags: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    needs_review: bool = True


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date_parser.parse(value).date()
    except (ValueError, OverflowError):
        return None


def validate_invoice(extraction: InvoiceExtraction, ocr_confidence: float) -> ValidationResult:
    flags: list[str] = []

    # --- required fields -----------------------------------------------
    if not extraction.invoice_number:
        flags.append("missing_invoice_number")
    if extraction.total is None:
        flags.append("missing_total")

    # --- date sanity ------------------------------------------------
    if extraction.invoice_date and _parse_date(extraction.invoice_date) is None:
        flags.append("unparseable_invoice_date")
    if extraction.due_date and _parse_date(extraction.due_date) is None:
        flags.append("unparseable_due_date")

    # --- arithmetic reconciliation ---------------------------------
    if extraction.line_items and extraction.subtotal is not None:
        computed_subtotal = sum(item.amount for item in extraction.line_items)
        if abs(computed_subtotal - extraction.subtotal) > AMOUNT_TOLERANCE:
            flags.append(
                f"line_items_sum_mismatch (line items sum to {computed_subtotal:.2f}, "
                f"subtotal says {extraction.subtotal:.2f})"
            )

    if (
        extraction.subtotal is not None
        and extraction.tax is not None
        and extraction.total is not None
    ):
        computed_total = extraction.subtotal + extraction.tax
        if abs(computed_total - extraction.total) > AMOUNT_TOLERANCE:
            flags.append(
                f"total_mismatch (subtotal + tax = {computed_total:.2f}, "
                f"total says {extraction.total:.2f})"
            )

    # --- per-field confidence ---------------------------------------
    low_conf_fields = [
        name
        for name, conf in extraction.field_confidences.items()
        if conf < FIELD_CONFIDENCE_FLOOR
    ]
    if low_conf_fields:
        flags.append(f"low_confidence_fields: {', '.join(sorted(low_conf_fields))}")

    # --- combine into an overall score -------------------------------
    field_confidences = list(extraction.field_confidences.values())
    mean_field_confidence = (
        sum(field_confidences) / len(field_confidences) if field_confidences else 0.5
    )
    overall_confidence = 0.4 * ocr_confidence + 0.6 * mean_field_confidence

    # Each failed business rule caps how confident we're allowed to say we
    # are, independent of what the raw score says.
    if flags:
        overall_confidence = min(overall_confidence, 0.6)

    needs_review = bool(flags) or overall_confidence < settings.REVIEW_CONFIDENCE_THRESHOLD

    return ValidationResult(
        passed=not flags,
        flags=flags,
        overall_confidence=round(overall_confidence, 3),
        needs_review=needs_review,
    )
