from app.core.config import Settings
from app.llm.contracts import ExtractionError, StructuredExtractor
from app.llm.ollama import OllamaAdapter
from app.llm.openai import OpenAIStructuredExtractor
from app.db.session import create_database_engine


def create_extractor(settings: Settings) -> StructuredExtractor:
    if settings.knowledge_ai_enabled:
        return OpenAIStructuredExtractor(settings, create_database_engine(settings))
    if settings.llm_provider != "ollama":
        raise ExtractionError("unsupported_provider")
    return OllamaAdapter(settings)
