from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import create_database_engine, get_session


def test_engine_is_lazy_and_uses_postgresql_timeouts():
    with patch("app.db.session.create_engine") as factory:
        engine = create_database_engine(Settings(_env_file=None))
        engine.connect.assert_not_called()
        options = factory.call_args.kwargs
    assert factory.call_args.args[0].startswith("postgresql+psycopg://")
    assert options["pool_pre_ping"] is True
    assert options["connect_args"]["connect_timeout"] == 3
    assert options["hide_parameters"] is True


def test_failed_request_rolls_back_and_closes_its_session():
    with patch("app.db.session.Session") as factory:
        session = factory.return_value.__enter__.return_value
        dependency = get_session(MagicMock())
        assert next(dependency) is session
        with pytest.raises(ValueError, match="failed operation"):
            dependency.throw(ValueError("failed operation"))
        session.rollback.assert_called_once()
        factory.return_value.__exit__.assert_called_once()


def test_domain_metadata_contains_requested_tables_and_acquisition_evidence():
    assert set(Base.metadata.tables) == {
        "companies",
        "reports",
        "document_chunks",
        "metric_definitions",
        "metric_observations",
        "targets",
        "themes",
        "company_themes",
        "extraction_runs",
        "validation_events",
        "report_discovery_runs",
        "report_artifacts",
        "document_pages",
        "document_tables",
        "pipeline_runs",
        "pipeline_jobs",
        "pipeline_events",
        "pipeline_domains",
        "benchmark_snapshots",
        "benchmark_components",
        "research_assessments",
        "benchmark_sessions",
        "benchmark_documents",
        "analysis_cache",
        "ai_calls",
        "knowledge_indexes",
        "knowledge_passages",
        "knowledge_jobs",
        "knowledge_answers",
        "report_collections",
        "peer_briefings",
    }
