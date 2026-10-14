from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    api_title: str = "Sustainability Benchmarking Intelligence API"
    reporting_year: int = Field(default=2025, ge=2000, le=2100)
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://sbi:sbi_local_dev@127.0.0.1:5432/sbi"
    )
    database_connect_timeout: int = Field(default=3, ge=1, le=30)
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=5, ge=0, le=20)
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    # The active knowledge product has one hosted provider; no silent fallback.
    ai_provider: Literal["openai"] = "openai"
    # Retained only for explicit legacy extraction CLI commands/tests.
    ollama_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:11434")
    llm_provider: Literal["ollama"] = "ollama"
    ollama_model: str | None = None
    # Knowledge research is opt-in and independent of legacy local extraction.
    knowledge_ai_enabled: bool = False
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    # Explicit allowlist prevents an accidental switch to a flagship/other allowance pool.
    openai_allowed_models: list[str] = ["gpt-5.4-mini-2026-03-17"]
    # This is a conservative Vero-only ceiling, not an OpenAI organization quota.
    openai_daily_token_limit: int = Field(default=2_000_000, ge=1, le=2_500_000)
    openai_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = (
        None
    )
    openai_timeout_seconds: float = Field(default=90, ge=1, le=180)
    openai_max_output_tokens: int = Field(default=2500, ge=128, le=16000)
    # Operator-supplied current rates, in USD / million tokens. Zero disables calls.
    openai_input_price: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    openai_output_price: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    report_analysis_model: str = ""
    report_analysis_input_price: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    report_analysis_output_price: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    knowledge_monthly_budget_usd: float = Field(
        default=0, ge=0, le=100, allow_inf_nan=False
    )
    knowledge_max_evidence_chars: int = Field(default=30000, ge=4000, le=60000)
    workbook_node: Path | None = None
    workbook_modules: Path | None = None

    @field_validator("openai_api_key")
    @classmethod
    def clean_api_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if key and (not key.isascii() or any(c.isspace() for c in key)):
            raise ValueError(
                "OPENAI_API_KEY must be a single token without internal whitespace"
            )
        return SecretStr(key)

    @field_validator("openai_model")
    @classmethod
    def safe_openai_model(cls, value: str) -> str:
        import re

        value = value.strip()
        if value and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,150}", value):
            raise ValueError("OPENAI_MODEL must be an explicit model ID")
        return value

    # Historic OpenRouter/ChatGPT credentials are still ignored.
    llm_context_tokens: int = Field(default=8192, ge=2048, le=16384)
    llm_timeout_seconds: float = Field(default=120, ge=0.1, le=600)
    llm_connect_timeout_seconds: float = Field(default=3, ge=0.1, le=10)
    llm_health_timeout_seconds: float = Field(default=5, ge=0.1, le=15)
    llm_retries: int = Field(default=1, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=1024, ge=16, le=8192)
    llm_max_output_chars: int = Field(default=16000, ge=128, le=100000)
    llm_max_response_bytes: int = Field(default=262144, ge=1024, le=2097152)
    llm_max_prompt_chars: int = Field(default=16000, ge=128, le=100000)
    reports_root: Path = BACKEND_DIR.parent / "data" / "reports"
    discovery_user_agent: str = "SustainabilityBenchmarkResearch/0.1"
    discovery_delay_seconds: float = Field(default=1.0, ge=0.5, le=60)
    discovery_timeout_seconds: float = Field(default=15.0, ge=1, le=60)
    discovery_retries: int = Field(default=2, ge=0, le=3)
    discovery_max_pages: int = Field(default=18, ge=1, le=100)
    discovery_max_depth: int = Field(default=3, ge=0, le=5)
    discovery_max_candidates: int = Field(default=100, ge=1, le=500)
    discovery_max_requests: int = Field(default=80, ge=5, le=300)
    discovery_max_download_mb: int = Field(default=100, ge=1, le=250)
    discovery_allow_js: bool = False
    discovery_search_fallback: bool = False
    discovery_verify_annual_content: bool = False
    discovery_sitemap_fallback: bool = False
    discovery_allow_prior_year: bool = False
    discovery_allow_unlabelled_year: bool = False
    # Explicit opt-in for RFC 9309 unavailable robots on exact company-linked PDFs.
    discovery_allow_unavailable_robots_for_linked_documents: bool = False
    discovery_search_delay_seconds: float = Field(default=3, ge=2, le=60)
    pipeline_company_workers: int = Field(default=2, ge=1, le=4)
    pipeline_parse_workers: int = Field(default=1, ge=1, le=2)
    pipeline_model_workers: int = Field(default=1, ge=1, le=2)
    pipeline_job_max_attempts: int = Field(default=3, ge=1, le=5)
    pipeline_fail_fast: bool = True
    pipeline_root: Path = BACKEND_DIR / "storage" / "pipeline"
    parse_chunk_chars: int = Field(default=2400, ge=200, le=10000)
    parse_max_pages: int = Field(default=1500, ge=1, le=5000)
    parse_max_page_chars: int = Field(default=300000, ge=1000, le=1000000)
    parse_max_document_chars: int = Field(default=25000000, ge=1000, le=100000000)
    parse_timeout_seconds: int = Field(default=300, ge=1, le=1800)
    parse_max_tables_per_page: int = Field(default=50, ge=1, le=200)
    parse_pdfplumber_fallback: bool = True
    # Only operator-confirmed, company-owned aliases. No automatically trusted CDNs.
    discovery_official_domains: dict[str, list[str]] = {}

    @field_validator("discovery_official_domains")
    @classmethod
    def explicit_owned_aliases(
        cls, values: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        import re
        from uuid import UUID

        for company_id, domains in values.items():
            UUID(company_id)
            for domain in domains:
                if (
                    not re.fullmatch(
                        r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", domain
                    )
                    or ".." in domain
                ):
                    raise ValueError(
                        "Official aliases must be lowercase DNS domains, without URLs or wildcards"
                    )
        return values

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError(
                "DATABASE_URL must be a valid PostgreSQL connection URL"
            ) from None
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError(
                "DATABASE_URL must use postgresql+psycopg and include a host and database"
            )
        return value

    @field_validator("cors_origins")
    @classmethod
    def require_explicit_origins(cls, values: list[str]) -> list[str]:
        from urllib.parse import urlsplit

        for value in values:
            parts = urlsplit(value)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.path not in {"", "/"}
                or parts.query
                or parts.fragment
                or parts.username
                or "*" in value
            ):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins")
        return [value.rstrip("/") for value in values]

    @field_validator("ollama_model")
    @classmethod
    def normalise_model_name(cls, value: str | None) -> str | None:
        import re

        value = value.strip() or None if value is not None else None
        if value and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:-]{0,199}", value):
            raise ValueError("OLLAMA_MODEL must be a plain installed model name")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def require_local_ollama(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        # No arbitrary DNS names, userinfo, paths, query secrets or cloud hosts.
        if (
            value.scheme != "http"
            or value.host not in {"localhost", "127.0.0.1", "[::1]"}
            or value.username is not None
            or value.password is not None
            or value.path not in {None, "", "/"}
            or value.query is not None
            or value.fragment is not None
            or value.port == 0
        ):
            raise ValueError("OLLAMA_BASE_URL must be a plain HTTP loopback origin")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
