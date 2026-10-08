"""Provenance-first company, acquisition, and future metric persistence."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Float,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATES_SQL = (
    "'extracted','validated','needs_review','not_reported','not_comparable','rejected'"
)


class Identity:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeIndex(Identity, Base):
    __tablename__ = "knowledge_indexes"
    report_id: Mapped[UUID] = mapped_column(ForeignKey("reports.id", ondelete="RESTRICT"), unique=True)
    parse_run_id: Mapped[UUID] = mapped_column(ForeignKey("extraction_runs.id", ondelete="RESTRICT"))
    report_sha256: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(30))
    quality: Mapped[dict[str, object]] = mapped_column(JSONB)


class KnowledgePassage(Identity, Base):
    __tablename__ = "knowledge_passages"
    index_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_indexes.id", ondelete="CASCADE"))
    page_id: Mapped[UUID] = mapped_column(ForeignKey("document_pages.id", ondelete="RESTRICT"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    locator: Mapped[dict[str, object]] = mapped_column(JSONB)
    search_vector: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english'::regconfig, content)", persisted=True))
    __table_args__ = (
        UniqueConstraint("index_id", "ordinal"),
        CheckConstraint("kind IN ('text','table')", name="kind"),
        CheckConstraint("ordinal >= 0 AND length(content) > 0", name="content"),
        Index("ix_knowledge_passages_search", "search_vector", postgresql_using="gin"),
        Index("ix_knowledge_passages_page", "page_id"),
    )


class KnowledgeJob(Identity, Base):
    __tablename__ = "knowledge_jobs"
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    year: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    outcome: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    __table_args__ = (
        UniqueConstraint("company_id", "year"),
        CheckConstraint("year BETWEEN 2000 AND 2100 AND attempts >= 0", name="bounds"),
        CheckConstraint("status IN ('pending','running','succeeded','partial','failed','needs_review','unavailable')", name="status"),
        Index("ix_knowledge_jobs_status", "status", "year"),
    )


class ReportCollection(Identity, Base):
    """Frozen bulk-acquisition cohort, independent of benchmark eligibility."""
    __tablename__ = "report_collections"
    year: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), server_default="pending")
    company_ids: Mapped[list[str]] = mapped_column(JSONB)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB)
    results: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("year BETWEEN 2000 AND 2100", name="year"),
        CheckConstraint("status IN ('pending','running','completed','completed_with_gaps','interrupted')", name="status"),
        Index("ix_report_collections_status", "status", "created_at"),
    )


class KnowledgeAnswer(Identity, Base):
    __tablename__ = "knowledge_answers"
    request_sha256: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(16, 8))
    charged_usd: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    usage: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed')", name="status"),
        CheckConstraint("reserved_usd >= 0 AND (charged_usd IS NULL OR charged_usd >= 0)", name="cost"),
        Index("ix_knowledge_answers_budget", "created_at", "status"),
    )


class PeerBriefing(Identity, Base):
    """Saved peer workspace with frozen sources and independently resumable topics."""
    __tablename__ = "peer_briefings"
    primary_company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), server_default="pending")
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    source_signature: Mapped[str] = mapped_column(String(64))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','paused','ready','partial','failed')", name="status"),
        Index("ix_peer_briefings_company_created", "primary_company_id", "created_at"),
    )


class BenchmarkSession(Identity, Base):
    __tablename__ = "benchmark_sessions"
    status: Mapped[str] = mapped_column(String(24), server_default="uploading", index=True)
    reporting_year: Mapped[int] = mapped_column(Integer)
    is_demo: Mapped[bool] = mapped_column(Boolean, server_default="false")
    unlocked: Mapped[bool] = mapped_column(Boolean, server_default="false")
    stages: Mapped[list[dict[str, object]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(80))
    cache_replay: Mapped[bool] = mapped_column(Boolean, server_default="false")
    __table_args__ = (CheckConstraint("status IN ('uploading','queued','running','failed','ready')",name="status"),)


class BenchmarkDocument(Identity, Base):
    __tablename__ = "benchmark_documents"
    session_id: Mapped[UUID] = mapped_column(ForeignKey("benchmark_sessions.id", ondelete="CASCADE"),index=True)
    company_name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str | None] = mapped_column(String(30))
    sector: Mapped[str | None] = mapped_column(String(100))
    primary: Mapped[bool] = mapped_column(Boolean, server_default="false")
    filename: Mapped[str] = mapped_column(String(240))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    report_id: Mapped[UUID | None] = mapped_column(ForeignKey("reports.id", ondelete="RESTRICT"))
    __table_args__ = (UniqueConstraint("session_id","sha256",name="uq_benchmark_document_hash"),UniqueConstraint("session_id","company_name",name="uq_benchmark_document_company"),)


class AnalysisCache(Identity, Base):
    __tablename__ = "analysis_cache"
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    payload_sha256: Mapped[str] = mapped_column(String(64))


class AICall(Identity, Base):
    __tablename__ = "ai_calls"
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("benchmark_sessions.id", ondelete="SET NULL"),index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(30))
    latency_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(16,8))
    error_code: Mapped[str | None] = mapped_column(String(80))
    fallback_from: Mapped[str | None] = mapped_column(String(200))


class PipelineRun(Identity, Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','interrupted','failed','succeeded')", name="status"
        ),
        CheckConstraint("checkpoint IN (5,20,50,100,200)", name="checkpoint"),
        Index(
            "ix_pipeline_runs_profile_checkpoint",
            "profile_sha256",
            "checkpoint",
            "created_at",
        ),
    )
    profile_sha256: Mapped[str] = mapped_column(String(64))
    checkpoint: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), server_default="running")
    requested_year: Mapped[int] = mapped_column(Integer)
    observation_year: Mapped[int] = mapped_column(Integer)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB)
    company_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    parent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="RESTRICT")
    )
    summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineJob(Identity, Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", "company_id", "stage", "metric_code"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','needs_review','unavailable','failed','blocked')",
            name="status",
        ),
        CheckConstraint(
            "stage IN ('discover','download','parse','retrieve','extract','validate','normalise','store')",
            name="stage",
        ),
        CheckConstraint("attempts >= 0", name="attempts"),
        Index("ix_pipeline_jobs_run_status", "run_id", "status"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="RESTRICT")
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    stage: Mapped[str] = mapped_column(String(24))
    metric_code: Mapped[str] = mapped_column(String(100), server_default="")
    status: Mapped[str] = mapped_column(String(24), server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    retryable: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    reason_code: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"
    __table_args__ = (Index("ix_pipeline_events_job_time", "job_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("pipeline_jobs.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(24))
    attempt: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PipelineDomain(Base):
    __tablename__ = "pipeline_domains"
    domain: Mapped[str] = mapped_column(String(253), primary_key=True)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Company(Identity, Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index(
            "uq_companies_listing",
            func.lower(text("exchange")),
            func.lower(text("ticker")),
            unique=True,
        ),
        Index("ix_companies_name", func.lower(text("company_name")), "id"),
        Index("ix_companies_sector_country", "sector", "country"),
        Index("ix_companies_cycle_active", "reporting_year", "active"),
        CheckConstraint(
            "btrim(company_name) <> '' AND btrim(ticker) <> '' AND btrim(exchange) <> ''",
            name="identity_not_blank",
        ),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="country_code"),
        CheckConstraint(
            "reporting_currency IS NULL OR reporting_currency ~ '^[A-Z]{3}$'",
            name="currency_code",
        ),
        CheckConstraint("reporting_year BETWEEN 2000 AND 2100", name="reporting_year"),
        CheckConstraint(
            "revenue_year IS NULL OR revenue_year BETWEEN 1900 AND 2100",
            name="revenue_year",
        ),
        CheckConstraint(
            "revenue IS NULL OR (revenue >= 0 AND revenue <> 'NaN'::numeric AND revenue_year IS NOT NULL AND reporting_currency IS NOT NULL)",
            name="revenue_context",
        ),
        CheckConstraint(
            "market_cap IS NULL OR (market_cap >= 0 AND market_cap <> 'NaN'::numeric AND reporting_currency IS NOT NULL)",
            name="market_cap_context",
        ),
        CheckConstraint(
            "sector IN ('Financial Services','Technology','Energy','Consumer / Retail','Industrials','Pharmaceuticals')",
            name="sector",
        ),
    )
    company_name: Mapped[str] = mapped_column(String(240))
    ticker: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(2))
    region: Mapped[str] = mapped_column(String(80))
    exchange: Mapped[str] = mapped_column(String(32))
    index: Mapped[str | None] = mapped_column(String(160))
    sector: Mapped[str] = mapped_column(String(80))
    industry: Mapped[str] = mapped_column(String(160))
    official_domain: Mapped[str] = mapped_column(String(253))
    investor_relations_url: Mapped[str | None] = mapped_column(Text)
    sustainability_url: Mapped[str | None] = mapped_column(Text)
    reporting_currency: Mapped[str | None] = mapped_column(String(3))
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    revenue_year: Mapped[int | None] = mapped_column(Integer)
    reporting_year: Mapped[int] = mapped_column(Integer)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    source_file: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int | None] = mapped_column(Integer)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Report(Identity, Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("id", "company_id", name="uq_reports_company_identity"),
        UniqueConstraint("discovery_run_id", "url_sha256", name="uq_reports_run_url"),
        Index("ix_reports_company_checksum", "company_id", "content_sha256"),
        Index("ix_reports_discovery_status", "requested_year", "status", "is_selected"),
        Index("ix_reports_artifact", "artifact_id"),
        Index(
            "uq_reports_run_selected",
            "discovery_run_id",
            unique=True,
            postgresql_where=text("is_selected AND discovery_run_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["discovery_run_id", "company_id", "requested_year"],
            [
                "report_discovery_runs.id",
                "report_discovery_runs.company_id",
                "report_discovery_runs.requested_year",
            ],
        ),
        CheckConstraint(
            "status IN ('discovered','downloaded','needs_review','unavailable','failed')",
            name="discovery_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="discovery_confidence",
        ),
        CheckConstraint(
            "requested_year IS NULL OR requested_year BETWEEN 2000 AND 2100",
            name="requested_year",
        ),
        CheckConstraint(
            "detected_year IS NULL OR detected_year BETWEEN 1900 AND 2100",
            name="detected_year",
        ),
        Index(
            "ix_reports_company_year_type",
            "company_id",
            "reporting_year",
            "report_type",
        ),
        ForeignKeyConstraint(
            ["supersedes_report_id", "company_id"], ["reports.id", "reports.company_id"]
        ),
        CheckConstraint("reporting_year BETWEEN 1900 AND 2100", name="year"),
        CheckConstraint("period_end >= period_start", name="period"),
        CheckConstraint("page_count IS NULL OR page_count > 0", name="page_count"),
        CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes >= 0", name="file_size"
        ),
        CheckConstraint(
            "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'",
            name="checksum",
        ),
        CheckConstraint("btrim(source_url) <> ''", name="source_required"),
        CheckConstraint(
            "supersedes_report_id IS NULL OR supersedes_report_id <> id",
            name="no_self_supersession",
        ),
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(Text)
    report_type: Mapped[str] = mapped_column(String(40))
    reporting_year: Mapped[int | None] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    publication_date: Mapped[date | None] = mapped_column(Date)
    language_code: Mapped[str] = mapped_column(String(10), server_default="en")
    source_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    discovered_from_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_key: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    document_version: Mapped[int] = mapped_column(Integer, server_default="1")
    supersedes_report_id: Mapped[UUID | None] = mapped_column(Uuid)
    download_status: Mapped[str] = mapped_column(String(32), server_default="pending")
    parse_status: Mapped[str] = mapped_column(String(32), server_default="pending")
    notes: Mapped[str] = mapped_column(Text, server_default="")
    discovery_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    requested_year: Mapped[int | None] = mapped_column(Integer)
    detected_year: Mapped[int | None] = mapped_column(Integer)
    url_sha256: Mapped[str | None] = mapped_column(String(64))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    selection_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), server_default="discovered")
    is_selected: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source_policy: Mapped[str | None] = mapped_column(String(40))
    artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("report_artifacts.id", ondelete="RESTRICT")
    )


class ReportDiscoveryRun(Identity, Base):
    __tablename__ = "report_discovery_runs"
    __table_args__ = (
        UniqueConstraint(
            "id", "company_id", "requested_year", name="uq_discovery_run_company_year"
        ),
        Index(
            "ix_discovery_company_year_time",
            "company_id",
            "requested_year",
            "created_at",
        ),
        CheckConstraint("requested_year BETWEEN 2000 AND 2100", name="requested_year"),
        CheckConstraint(
            "status IN ('discovered','downloaded','needs_review','unavailable','failed')",
            name="status",
        ),
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    requested_year: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    selection_reason: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(40))
    sources: Mapped[list[str]] = mapped_column(JSONB)
    diagnostics: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    pages_visited: Mapped[int] = mapped_column(Integer, server_default="0")
    http_requests: Mapped[int] = mapped_column(Integer, server_default="0")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportArtifact(Identity, Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        UniqueConstraint("content_sha256"),
        UniqueConstraint("storage_key"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="checksum"),
        CheckConstraint("file_size_bytes > 0", name="file_size"),
    )
    content_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(120))


class ExtractionRun(Identity, Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        UniqueConstraint("id", "report_id", name="uq_runs_report_identity"),
        UniqueConstraint("idempotency_key"),
        Index("ix_runs_report_stage_status", "report_id", "stage", "status"),
        CheckConstraint(
            "stage IN ('parsing','retrieval','extraction','normalisation','quality')",
            name="stage",
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="status",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="time_order"
        ),
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="RESTRICT")
    )
    parent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="RESTRICT"), index=True
    )
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), server_default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(128))
    input_sha256: Mapped[str] = mapped_column(String(64))
    model_provider: Mapped[str | None] = mapped_column(String(80))
    model_name: Mapped[str | None] = mapped_column(String(160))
    model_digest: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str] = mapped_column(String(80))
    code_version: Mapped[str] = mapped_column(String(80))
    parameters: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[dict[str, object] | None] = mapped_column(JSONB)


class DocumentChunk(Identity, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("id", "report_id", name="uq_chunks_report_identity"),
        UniqueConstraint("report_id", "parse_run_id", "chunk_index"),
        ForeignKeyConstraint(
            ["parse_run_id", "report_id"],
            ["extraction_runs.id", "extraction_runs.report_id"],
        ),
        Index("ix_chunks_report_page", "report_id", "physical_page_start"),
        Index("ix_chunks_parse_run", "parse_run_id"),
        CheckConstraint(
            "physical_page_start >= 1 AND physical_page_end >= physical_page_start",
            name="page_range",
        ),
        CheckConstraint("chunk_index >= 0", name="chunk_index"),
        CheckConstraint("chunk_type IN ('text','table')", name="type"),
        CheckConstraint("source_text_layer IN ('ordered_text','raw_text')", name="source_text_layer"),
        ForeignKeyConstraint(
            ["document_page_id", "report_id", "parse_run_id", "physical_page_start"],
            [
                "document_pages.id",
                "document_pages.report_id",
                "document_pages.parse_run_id",
                "document_pages.page_number",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "document_page_id IS NULL OR (physical_page_start = physical_page_end AND source_char_start IS NOT NULL AND source_char_end IS NOT NULL AND source_char_start >= 0 AND source_char_end > source_char_start)",
            name="page_provenance",
        ),
        Index("ix_chunks_document_page", "document_page_id"),
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="RESTRICT")
    )
    parse_run_id: Mapped[UUID] = mapped_column(Uuid)
    chunk_index: Mapped[int] = mapped_column(Integer)
    physical_page_start: Mapped[int] = mapped_column(Integer)
    physical_page_end: Mapped[int] = mapped_column(Integer)
    printed_page_label: Mapped[str | None] = mapped_column(String(80))
    section_title: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    chunk_type: Mapped[str] = mapped_column(String(16))
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(80))
    table_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    document_page_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_char_start: Mapped[int | None] = mapped_column(Integer)
    source_char_end: Mapped[int | None] = mapped_column(Integer)
    source_text_layer: Mapped[str] = mapped_column(String(20), server_default="ordered_text")
    source_spans: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)


class DocumentPage(Identity, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "parse_run_id", "page_number", name="uq_pages_run_number"
        ),
        UniqueConstraint(
            "id", "report_id", "parse_run_id", "page_number", name="uq_pages_provenance"
        ),
        ForeignKeyConstraint(
            ["parse_run_id", "report_id"],
            ["extraction_runs.id", "extraction_runs.report_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_pages_report_number", "report_id", "page_number"),
        Index("ix_pages_run_status", "parse_run_id", "status"),
        CheckConstraint("page_number >= 1", name="page_number"),
        CheckConstraint("width_points > 0 AND height_points > 0", name="dimensions"),
        CheckConstraint("status IN ('parsed','needs_ocr','failed')", name="status"),
        CheckConstraint(
            "raw_text_sha256 ~ '^[0-9a-f]{64}$' AND ordered_text_sha256 ~ '^[0-9a-f]{64}$'",
            name="hashes",
        ),
        CheckConstraint(
            "text_characters = char_length(raw_text)", name="text_characters"
        ),
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="RESTRICT")
    )
    parse_run_id: Mapped[UUID] = mapped_column(Uuid)
    page_number: Mapped[int] = mapped_column(Integer)
    printed_page_label: Mapped[str | None] = mapped_column(String(80))
    width_points: Mapped[float] = mapped_column(Float)
    height_points: Mapped[float] = mapped_column(Float)
    rotation: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    raw_text_sha256: Mapped[str] = mapped_column(String(64))
    ordered_text: Mapped[str] = mapped_column(Text)
    ordered_text_sha256: Mapped[str] = mapped_column(String(64))
    text_characters: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    headings: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    layout: Mapped[dict[str, object]] = mapped_column(JSONB)
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(80))


class DocumentTable(Identity, Base):
    __tablename__ = "document_tables"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_page_id", "report_id", "parse_run_id", "page_number"],
            [
                "document_pages.id",
                "document_pages.report_id",
                "document_pages.parse_run_id",
                "document_pages.page_number",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "document_page_id", "table_index", name="uq_tables_page_index"
        ),
        Index("ix_tables_report_page", "report_id", "page_number"),
        Index("ix_tables_parse_run", "parse_run_id"),
        CheckConstraint(
            "table_index >= 0 AND row_count >= 2 AND column_count >= 2", name="shape"
        ),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="checksum"),
        CheckConstraint("validation_state = 'needs_review'", name="unverified"),
    )
    document_page_id: Mapped[UUID] = mapped_column(Uuid)
    report_id: Mapped[UUID] = mapped_column(Uuid)
    parse_run_id: Mapped[UUID] = mapped_column(Uuid)
    page_number: Mapped[int] = mapped_column(Integer)
    table_index: Mapped[int] = mapped_column(Integer)
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    cells: Mapped[list[list[str | None]]] = mapped_column(JSONB)
    bbox: Mapped[list[float]] = mapped_column(JSONB)
    cell_bboxes: Mapped[list[list[float] | None]] = mapped_column(JSONB)
    header_metadata: Mapped[dict[str, object]] = mapped_column(JSONB)
    extraction_metadata: Mapped[dict[str, object]] = mapped_column(JSONB)
    content_sha256: Mapped[str] = mapped_column(String(64))
    extraction_method: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(80))
    validation_state: Mapped[str] = mapped_column(
        String(24), server_default="needs_review"
    )


class MetricDefinition(Identity, Base):
    __tablename__ = "metric_definitions"
    __table_args__ = (
        UniqueConstraint("metric_code", "definition_version"),
        Index(
            "ix_metrics_catalogue_category",
            "catalogue_version",
            "category",
            "metric_code",
        ),
        CheckConstraint(
            "catalogue_version IS NULL OR (definition_version > 0 AND "
            "category IS NOT NULL AND category IN ('climate','energy','targets','water','waste','governance','social','supply_chain','disclosure_quality') AND "
            "allowed_units IS NOT NULL AND jsonb_typeof(allowed_units) = 'array' AND "
            "aliases IS NOT NULL AND jsonb_typeof(aliases) = 'array' AND "
            "normalisation_rule IS NOT NULL AND jsonb_typeof(normalisation_rule) = 'object' AND "
            "validation_constraints IS NOT NULL AND jsonb_typeof(validation_constraints) = 'object' AND "
            "comparability_warning IS NOT NULL AND btrim(comparability_warning) <> '' AND "
            "score_eligibility IS NOT NULL AND score_eligibility IN ('not_eligible','conditional') AND "
            "value_type IN ('decimal','integer','boolean','enum','text','object') AND "
            "directionality IN ('lower','higher','none') AND "
            "evidence_kind IS NOT NULL AND evidence_kind IN ('performance','target','governance','disclosure','programme') AND "
            "normalisation_rule_version IS NOT NULL AND validation_rule_version IS NOT NULL)",
            name="catalogue_contract",
        ),
        CheckConstraint(
            "catalogue_version IS NULL OR score_eligibility <> 'conditional' OR "
            "(evidence_kind = 'performance' AND value_type IN ('decimal','integer') AND "
            "directionality IN ('lower','higher') AND jsonb_array_length(required_comparison_dimensions) > 0)",
            name="conditional_scoring",
        ),
    )
    metric_code: Mapped[str] = mapped_column(String(100))
    definition_version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    sector_applicability: Mapped[list[str]] = mapped_column(JSONB)
    quantity_kind: Mapped[str] = mapped_column(String(32))
    canonical_unit: Mapped[str | None] = mapped_column(String(80))
    value_type: Mapped[str] = mapped_column(String(32))
    directionality: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(80))
    required_comparison_dimensions: Mapped[list[str]] = mapped_column(JSONB)
    normalisation_rule_version: Mapped[str | None] = mapped_column(String(80))
    validation_rule_version: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Nullable only for pre-catalogue/legacy definitions; catalogue rows require
    # every contract field. No guessed metadata is backfilled into old evidence.
    catalogue_version: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(32))
    evidence_kind: Mapped[str | None] = mapped_column(String(32))
    allowed_units: Mapped[list[str] | None] = mapped_column(JSONB)
    aliases: Mapped[list[str] | None] = mapped_column(JSONB)
    normalisation_rule: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    comparability_warning: Mapped[str | None] = mapped_column(Text)
    score_eligibility: Mapped[str | None] = mapped_column(String(32))
    validation_constraints: Mapped[dict[str, object] | None] = mapped_column(JSONB)


class Evidence:
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    report_id: Mapped[UUID] = mapped_column(Uuid)
    document_chunk_id: Mapped[UUID] = mapped_column(Uuid)
    extraction_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    reporting_year: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    source_physical_page: Mapped[int] = mapped_column(Integer)
    source_printed_page_label: Mapped[str | None] = mapped_column(String(80))
    supporting_excerpt: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confidence_notes: Mapped[str | None] = mapped_column(Text)
    validation_state: Mapped[str] = mapped_column(
        String(32), server_default="extracted"
    )
    notes: Mapped[str] = mapped_column(Text, server_default="")


def evidence_constraints(table: str) -> tuple[object, ...]:
    return (
        ForeignKeyConstraint(
            ["report_id", "company_id"], ["reports.id", "reports.company_id"]
        ),
        ForeignKeyConstraint(
            ["document_chunk_id", "report_id"],
            ["document_chunks.id", "document_chunks.report_id"],
        ),
        ForeignKeyConstraint(
            ["extraction_run_id", "report_id"],
            ["extraction_runs.id", "extraction_runs.report_id"],
        ),
        Index(f"ix_{table}_report", "report_id"),
        Index(f"ix_{table}_chunk", "document_chunk_id"),
        Index(f"ix_{table}_run", "extraction_run_id"),
        CheckConstraint(f"validation_state IN ({STATES_SQL})", name="validation_state"),
        CheckConstraint("reporting_year BETWEEN 1900 AND 2100", name="year"),
        CheckConstraint("source_physical_page >= 1", name="page"),
        CheckConstraint(
            "btrim(source_url) <> '' AND btrim(supporting_excerpt) <> '' AND btrim(extraction_method) <> ''",
            name="evidence_required",
        ),
        CheckConstraint(
            "(confidence IS NOT NULL AND confidence BETWEEN 0 AND 1) OR (confidence IS NULL AND confidence_notes IS NOT NULL AND btrim(confidence_notes) <> '')",
            name="confidence",
        ),
    )


class MetricObservation(Evidence, Identity, Base):
    __tablename__ = "metric_observations"
    __table_args__ = (
        *evidence_constraints("metric_observations"),
        UniqueConstraint("idempotency_key"),
        Index(
            "ix_observations_company_year_metric_state",
            "company_id",
            "reporting_year",
            "metric_definition_id",
            "validation_state",
        ),
        Index(
            "ix_observations_metric_year_group",
            "metric_definition_id",
            "reporting_year",
            "comparison_group_key",
        ),
        CheckConstraint(
            "normalised_value IS NULL OR (normalised_value <> 'NaN'::numeric AND normalised_unit IS NOT NULL AND raw_value IS NOT NULL AND raw_unit IS NOT NULL AND normalisation_rule_version IS NOT NULL)",
            name="normalised_provenance",
        ),
        CheckConstraint(
            "validation_state <> 'not_reported' OR (raw_value IS NULL AND normalised_value IS NULL)",
            name="missing_is_not_zero",
        ),
        CheckConstraint("period_end >= period_start", name="period"),
        CheckConstraint(
            "value_qualifier IN ('exact','approximate','less_than','greater_than','range')",
            name="qualifier",
        ),
        CheckConstraint(
            "validation_state NOT IN ('extracted','validated','not_comparable') OR (raw_value IS NOT NULL AND btrim(raw_value) <> '')",
            name="value_required",
        ),
    )
    metric_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("metric_definitions.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    raw_value: Mapped[str | None] = mapped_column(Text)
    raw_unit: Mapped[str | None] = mapped_column(Text)
    normalised_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    normalised_unit: Mapped[str | None] = mapped_column(String(80))
    value_qualifier: Mapped[str] = mapped_column(String(24), server_default="exact")
    normalisation_rule_version: Mapped[str | None] = mapped_column(String(80))
    organisational_boundary: Mapped[str | None] = mapped_column(Text)
    consolidation_basis: Mapped[str | None] = mapped_column(String(80))
    scope: Mapped[str | None] = mapped_column(String(80))
    scope2_method: Mapped[str | None] = mapped_column(String(40))
    scope3_categories: Mapped[list[int] | None] = mapped_column(JSONB)
    intensity_denominator: Mapped[str | None] = mapped_column(Text)
    denominator_unit: Mapped[str | None] = mapped_column(String(80))
    currency_code: Mapped[str | None] = mapped_column(String(3))
    currency_basis: Mapped[str | None] = mapped_column(Text)
    coverage_description: Mapped[str | None] = mapped_column(Text)
    methodology_version: Mapped[str | None] = mapped_column(String(80))
    is_historical_comparative: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    is_restated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    supersedes_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("metric_observations.id", ondelete="RESTRICT"), index=True
    )
    compatibility_state: Mapped[str] = mapped_column(
        String(32), server_default="unchecked"
    )
    compatibility_rule_version: Mapped[str | None] = mapped_column(String(80))
    comparison_group_key: Mapped[str | None] = mapped_column(String(200))
    # Explicitly reviewed catalogue dimensions absent from the original schema.
    # Never populated by the model or inferred by the benchmarking engine.
    comparison_context: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class BenchmarkSnapshot(Identity, Base):
    __tablename__ = "benchmark_snapshots"
    __table_args__ = (
        UniqueConstraint("input_sha256"),
        Index("ix_benchmark_snapshots_year_created", "reporting_year", "created_at"),
        CheckConstraint("reporting_year BETWEEN 2000 AND 2100", name="year"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="checksum"),
    )
    reporting_year: Mapped[int] = mapped_column(Integer)
    methodology_version: Mapped[str] = mapped_column(String(80))
    input_sha256: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB)
    results: Mapped[dict[str, object]] = mapped_column(JSONB)


class ResearchAssessment(Identity, Base):
    """Bounded study decisions; measurements remain in observations/targets."""
    __tablename__ = "research_assessments"
    __table_args__ = (
        UniqueConstraint("study_id", "company_id", "metric_code"),
        CheckConstraint("status IN ('NOT_ASSESSED','NOT_FOUND_IN_REVIEWED_SOURCES','NOT_REPORTED','NOT_COMPARABLE','VALIDATED','NEEDS_REVIEW')", name="status"),
        CheckConstraint("num_nonnulls(observation_id, target_id) <= 1", name="one_value"),
        CheckConstraint("status <> 'VALIDATED' OR num_nonnulls(observation_id, target_id) = 1", name="validated_evidence"),
        CheckConstraint("status <> 'VALIDATED' OR comparison_group IS NOT NULL", name="stated_comparison"),
        Index("ix_research_assessments_study_status", "study_id", "status"),
    )
    study_id: Mapped[str] = mapped_column(String(80))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    metric_code: Mapped[str] = mapped_column(String(100))
    observation_id: Mapped[UUID | None] = mapped_column(ForeignKey("metric_observations.id", ondelete="RESTRICT"))
    target_id: Mapped[UUID | None] = mapped_column(ForeignKey("targets.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(40))
    comparison_group: Mapped[str | None] = mapped_column(String(200))
    comparability_note: Mapped[str] = mapped_column(Text)
    review: Mapped[dict[str, object]] = mapped_column(JSONB)


class BenchmarkComponent(Identity, Base):
    __tablename__ = "benchmark_components"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "company_id", "component"),
        Index("ix_benchmark_components_company_snapshot", "company_id", "snapshot_id"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="score"),
        CheckConstraint("weight BETWEEN 0 AND 1", name="weight"),
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("benchmark_snapshots.id", ondelete="RESTRICT")
    )
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT")
    )
    component: Mapped[str] = mapped_column(String(80))
    score: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    reason: Mapped[str | None] = mapped_column(Text)
    formula: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB)


class Target(Evidence, Identity, Base):
    __tablename__ = "targets"
    __table_args__ = (
        *evidence_constraints("targets"),
        Index(
            "ix_targets_company_year_metric",
            "company_id",
            "reporting_year",
            "metric_definition_id",
        ),
        Index("ix_targets_metric", "metric_definition_id"),
        CheckConstraint("target_year BETWEEN 1900 AND 2200", name="target_year"),
        CheckConstraint(
            "baseline_year IS NULL OR (baseline_year BETWEEN 1900 AND 2200 AND baseline_year <= target_year)",
            name="baseline_year",
        ),
        CheckConstraint(
            "reduction_percent IS NULL OR reduction_percent BETWEEN 0 AND 100",
            name="reduction_percent",
        ),
        CheckConstraint(
            "target_normalised_value IS NULL OR (target_raw_value IS NOT NULL AND target_raw_unit IS NOT NULL AND target_normalised_unit IS NOT NULL AND normalisation_rule_version IS NOT NULL)",
            name="target_provenance",
        ),
        CheckConstraint(
            "baseline_normalised_value IS NULL OR (baseline_raw_value IS NOT NULL AND baseline_raw_unit IS NOT NULL AND baseline_normalised_unit IS NOT NULL AND baseline_year IS NOT NULL AND normalisation_rule_version IS NOT NULL)",
            name="baseline_provenance",
        ),
    )
    metric_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("metric_definitions.id", ondelete="RESTRICT")
    )
    target_type: Mapped[str] = mapped_column(String(40))
    baseline_year: Mapped[int | None] = mapped_column(Integer)
    baseline_raw_value: Mapped[str | None] = mapped_column(Text)
    baseline_raw_unit: Mapped[str | None] = mapped_column(Text)
    baseline_normalised_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    baseline_normalised_unit: Mapped[str | None] = mapped_column(String(80))
    target_year: Mapped[int] = mapped_column(Integer)
    target_raw_value: Mapped[str | None] = mapped_column(Text)
    target_raw_unit: Mapped[str | None] = mapped_column(Text)
    target_normalised_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 12))
    target_normalised_unit: Mapped[str | None] = mapped_column(String(80))
    normalisation_rule_version: Mapped[str | None] = mapped_column(String(80))
    reduction_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    organisational_boundary: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(String(80))
    scope2_method: Mapped[str | None] = mapped_column(String(40))
    scope3_categories: Mapped[list[int] | None] = mapped_column(JSONB)
    target_coverage: Mapped[str | None] = mapped_column(Text)


class Theme(Identity, Base):
    __tablename__ = "themes"
    __table_args__ = (UniqueConstraint("theme_code", "taxonomy_version"),)
    theme_code: Mapped[str] = mapped_column(String(100))
    taxonomy_version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    parent_theme_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("themes.id", ondelete="RESTRICT"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class CompanyTheme(Evidence, Identity, Base):
    __tablename__ = "company_themes"
    __table_args__ = (
        *evidence_constraints("company_themes"),
        UniqueConstraint(
            "company_id", "theme_id", "reporting_year", "document_chunk_id"
        ),
        Index("ix_company_themes_theme_year", "theme_id", "reporting_year"),
    )
    theme_id: Mapped[UUID] = mapped_column(ForeignKey("themes.id", ondelete="RESTRICT"))


class ValidationEvent(Base):
    __tablename__ = "validation_events"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(metric_observation_id, target_id, company_theme_id) = 1",
            name="exactly_one_subject",
        ),
        CheckConstraint(f"new_state IN ({STATES_SQL})", name="new_state"),
        CheckConstraint(
            f"previous_state IS NULL OR previous_state IN ({STATES_SQL})",
            name="previous_state",
        ),
        CheckConstraint("actor_type IN ('rule','human')", name="actor_type"),
        CheckConstraint(
            "btrim(reason) <> '' AND btrim(actor_reference) <> ''", name="attribution"
        ),
        Index("ix_validation_observation_time", "metric_observation_id", "created_at"),
        Index("ix_validation_target_time", "target_id", "created_at"),
        Index("ix_validation_theme_time", "company_theme_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    metric_observation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("metric_observations.id", ondelete="RESTRICT")
    )
    target_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="RESTRICT")
    )
    company_theme_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_themes.id", ondelete="RESTRICT")
    )
    previous_state: Mapped[str | None] = mapped_column(String(32))
    new_state: Mapped[str] = mapped_column(String(32))
    rule_code: Mapped[str | None] = mapped_column(String(80))
    rule_version: Mapped[str | None] = mapped_column(String(80))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_reference: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
