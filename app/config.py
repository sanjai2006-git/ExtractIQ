import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.environ.get(
        "OPENROUTER_MODEL",
        "openai/gpt-oss-20b:free"
    )

    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./extraction.db"
    )

    STORAGE_DIR: Path = Path(
        os.environ.get("STORAGE_DIR", "./storage")
    )

    REVIEW_CONFIDENCE_THRESHOLD: float = float(
        os.environ.get(
            "REVIEW_CONFIDENCE_THRESHOLD",
            "0.85"
        )
    )

    OCR_LOW_CONFIDENCE_THRESHOLD: float = 0.75


settings = Settings()
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)