"""
Turns parsed document text into a typed, validated extraction
using an OpenRouter model with structured JSON output.
"""

from typing import Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)

EXTRACTION_SYSTEM_PROMPT = """You are a precise document data extraction engine.

Rules:
- Extract only what is actually present in the document text.
- Never guess or fabricate values.
- If a field is missing, illegible, or ambiguous, return null.
- Numbers must be plain numbers without currency symbols or commas.
- Return valid JSON matching the requested schema.
"""


class ExtractionError(Exception):
    pass


def extract(
    document_text: str,
    schema: Type[T],
    doc_type_label: str = "document",
) -> T:

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"Extract the {doc_type_label} fields from this "
                    f"document text:\n\n{document_text}"
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": f"extract_{doc_type_label}",
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        },
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )

    if response.status_code != 200:
        raise ExtractionError(
            f"OpenRouter API error: {response.status_code} "
            f"{response.text}"
        )

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise ExtractionError(
            "OpenRouter did not return valid model output."
        ) from e

    try:
        return schema.model_validate_json(content)
    except ValidationError as e:
        raise ExtractionError(
            f"Extracted data failed schema validation: {e}"
        ) from e