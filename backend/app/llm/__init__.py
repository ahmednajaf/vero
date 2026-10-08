"""Provider-independent structured extraction contracts and composition root."""

from app.llm.contracts import (
    ExtractionError,
    Prompt,
    StructuredExtractor,
    StructuredResult,
)
from app.llm.factory import create_extractor

__all__ = [
    "ExtractionError",
    "Prompt",
    "StructuredExtractor",
    "StructuredResult",
    "create_extractor",
]
