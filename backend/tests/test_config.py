import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_connection_string_is_redacted():
    settings = Settings(_env_file=None)
    assert "sbi_local_dev" not in repr(settings)
    assert "sbi_local_dev" not in settings.model_dump_json()


@pytest.mark.parametrize("url", ["sqlite:///demo.db", "not-a-url", "postgresql+psycopg://localhost/"])
def test_rejects_non_postgresql_or_incomplete_urls(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=SecretStr(url))


@pytest.mark.parametrize("origin", ["*", "https://example.com/path", "https://user:password@example.com"])
def test_requires_explicit_cors_origins(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=[origin])


def test_environment_configuration_and_model_whitespace(monkeypatch):
    monkeypatch.setenv("REPORTING_YEAR", "2026")
    monkeypatch.setenv("OLLAMA_MODEL", "  qwen3:14b  ")
    settings = Settings(_env_file=None)
    assert settings.reporting_year == 2026
    assert settings.ollama_model == "qwen3:14b"
    assert str(settings.ollama_base_url).rstrip("/") == "http://localhost:11434"


def test_model_is_optional_until_extraction_is_implemented(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert Settings(_env_file=None).ollama_model is None
    assert Settings(_env_file=None, ollama_model=" ").ollama_model is None


def test_invalid_reporting_cycle_fails_early():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reporting_year=1800)
