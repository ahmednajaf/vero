"""Mocked batch tests; never require external sites or an installed model."""

import argparse
import asyncio
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    DocumentChunk,
    DocumentPage,
    ExtractionRun,
    MetricDefinition,
    MetricObservation,
    PipelineJob,
    PipelineRun,
    Report,
)
from app.pipeline import cli
from app.pipeline.export import export, finish, safe_csv, snapshot
from app.pipeline.ledger import recover, state, transition
from app.pipeline.runner import (
    batch_lock,
    execute_run,
    get_run,
    profile,
    select_companies,
    verify_artifacts,
)
from app.pipeline.stages import Services, StageFailure, require_primary_report
from app.pipeline.throttle import DomainPacer
from app.services.company_import import import_companies
from test_extraction import (
    FakeExtractor,
    IDENTITY,
    FIXTURES,
    candidate,
    run,
    saved_report,  # noqa: F401 -- shared pytest fixture
)  # noqa: F401
from app.llm.contracts import ExtractionError

__all__ = ["saved_report"]  # Re-export the shared pytest fixture for collection.


@pytest.fixture
def universe(db_engine, company_row, csv_file):
    rows = []
    for i in range(20):
        rows.append(
            {
                **company_row,
                "id": str(UUID(int=i + 1)),
                "company_name": f"Fictional Company {i:02d}",
                "ticker": f"F{i:02d}",
                "country": "GB" if i < 10 else "US",
                "sector": "Industrials" if i < 10 else "Technology",
            }
        )
    assert import_companies(csv_file(rows), db_engine).committed
    return select_companies(db_engine, 20)


@pytest.fixture
def configuration(tmp_path):
    return Settings(
        _env_file=None,
        ollama_model=IDENTITY.name,
        reports_root=tmp_path / "reports",
        pipeline_root=tmp_path / "batches",
        pipeline_company_workers=2,
        pipeline_fail_fast=False,
    )


class FakeServices:
    """Fictional evidence, real ledger/foreign keys/exports. No I/O transport."""

    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.calls = Counter()
        self.fail_stage = None
        self.fail_company = None
        self.retryable = True
        self.no_values = False
        self.active = 0
        self.max_active = 0

    def check(self, stage, company):
        self.calls[stage, str(company)] += 1
        if self.fail_stage == stage and (
            self.fail_company is None or self.fail_company == str(company)
        ):
            raise StageFailure(
                "timeout" if self.retryable else "access_control",
                retryable=self.retryable,
            )

    def discover(self, company, year):
        self.check("discover", company)
        with Session(self.engine) as session, session.begin():
            report = session.scalar(select(Report).where(Report.company_id == company))
            if not report:
                body = b"Fictional report fixture bytes; not a real company PDF"
                path = self.settings.reports_root / str(company) / "fixture.pdf"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                report = Report(
                    company_id=company,
                    title="Fictional fixture",
                    report_type="sustainability",
                    source_url="https://example.com/fixture.pdf",
                    requested_year=year,
                    status="downloaded",
                    content_sha256=hashlib.sha256(body).hexdigest(),
                    storage_key=str(path.relative_to(self.settings.reports_root)),
                    file_size_bytes=len(body),
                    page_count=1,
                )
                session.add(report)
                session.flush()
                parse = ExtractionRun(
                    report_id=report.id,
                    stage="parsing",
                    status="succeeded",
                    idempotency_key=uuid4().hex,
                    input_sha256=report.content_sha256,
                    code_version="fixture",
                    schema_version="fixture",
                )
                session.add(parse)
                session.flush()
                session.add(
                    DocumentChunk(
                        report_id=report.id,
                        parse_run_id=parse.id,
                        chunk_index=0,
                        physical_page_start=1,
                        physical_page_end=1,
                        text="2024 Scope 1 emissions: 12 tCO2e.",
                        text_sha256="b" * 64,
                        chunk_type="text",
                        parser_name="fixture",
                        parser_version="1",
                    )
                )
            return {"report_id": str(report.id)}

    def company(self, report):
        with Session(self.engine) as session:
            return session.get(Report, report).company_id

    def download(self, report):
        self.check("download", self.company(report))
        return {"report_id": str(report)}

    async def parse(self, report):
        self.check("parse", self.company(report))
        self.active += 1
        self.max_active = max(self.active, self.max_active)
        await asyncio.sleep(0.005)
        self.active -= 1
        return {"report_id": str(report), "quality": {"pages_with_text": 1}}

    def retrieval(self, report, metric, year, top_k):
        self.check("retrieve", self.company(report))
        return {"candidates": [{"page": 1}]}

    async def extract(self, report, metric, year, top_k):
        self.check("extract", self.company(report))
        with Session(self.engine) as session, session.begin():
            source = session.get(Report, report)
            chunk = session.scalar(
                select(DocumentChunk).where(DocumentChunk.report_id == report)
            )
            definition = session.scalar(
                select(MetricDefinition).where(MetricDefinition.metric_code == metric)
            )
            extraction = ExtractionRun(
                report_id=report,
                parent_run_id=chunk.parse_run_id,
                stage="extraction",
                status="succeeded",
                idempotency_key=uuid4().hex,
                input_sha256=source.content_sha256,
                model_provider="ollama",
                model_name=IDENTITY.name,
                model_digest=IDENTITY.digest,
                prompt_version="test",
                code_version="metric-extraction-fixture",
                schema_version="test",
                parameters={"year": year},
                output_summary={"observation_count": 0 if self.no_values else 1},
                finished_at=datetime.now(UTC),
            )
            session.add(extraction)
            session.flush()
            if not self.no_values:
                session.add(
                    MetricObservation(
                        company_id=source.company_id,
                        report_id=report,
                        document_chunk_id=chunk.id,
                        extraction_run_id=extraction.id,
                        metric_definition_id=definition.id,
                        idempotency_key=uuid4().hex,
                        reporting_year=year,
                        source_url=source.source_url,
                        source_physical_page=1,
                        supporting_excerpt=chunk.text,
                        extraction_method="local_structured_llm",
                        confidence=Decimal(".5"),
                        confidence_notes="{}",
                        notes="{}",
                        validation_state="needs_review",
                        raw_value="12",
                        raw_unit="tCO2e",
                        normalised_value=Decimal("12"),
                        normalised_unit="tCO2e",
                        normalisation_rule_version="fixture",
                    )
                )
            return {"extraction_run_id": str(extraction.id)}

    def receipt(self, extraction, stage):
        return Services.receipt(self, extraction, stage)


def parameters(settings, metrics=("scope_1_emissions",)):
    return profile(
        settings,
        IDENTITY,
        2025,
        2024,
        {"sector": None, "country": None, "company": []},
        metrics,
        1,
    )


def setup_run(engine, settings, universe, number=5, parent=None):
    return get_run(engine, parameters(settings), universe[:number], number, parent)[0]


def test_successful_5_then_20_reuses_completed_prefix(
    db_engine, configuration, universe
):
    services = FakeServices(db_engine, configuration)
    five = setup_run(db_engine, configuration, universe)
    asyncio.run(execute_run(db_engine, configuration, five, services))
    verify_artifacts(db_engine, configuration, five)
    assert finish(db_engine, five)["summary"]["checkpoint_passed"]
    twenty = setup_run(db_engine, configuration, universe, 20, five)
    asyncio.run(execute_run(db_engine, configuration, twenty, services))
    payload = finish(db_engine, twenty)
    assert payload["summary"]["companies_total"] == 20
    assert (
        payload["summary"]["extracted"] == 20 and payload["summary"]["validated"] == 0
    )
    assert payload["summary"]["checkpoint_passed"]
    assert all(count == 1 for count in services.calls.values())
    assert services.max_active <= 2
    assert get_run(db_engine, parameters(configuration), universe[:5], 5, None) == (
        five,
        True,
    )
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(MetricObservation)) == 20


def test_resume_only_incomplete_stage_and_preserve_failures(
    db_engine, configuration, universe
):
    services = FakeServices(db_engine, configuration)
    services.fail_stage = "parse"
    services.fail_company = universe[0]["id"]
    identifier = setup_run(db_engine, configuration, universe)
    asyncio.run(execute_run(db_engine, configuration, identifier, services))
    assert not finish(db_engine, identifier)["summary"]["checkpoint_passed"]
    services.fail_stage = None
    asyncio.run(execute_run(db_engine, configuration, identifier, services))
    payload = finish(db_engine, identifier)
    assert payload["summary"]["checkpoint_passed"]
    assert services.calls["discover", universe[0]["id"]] == 1
    assert services.calls["parse", universe[0]["id"]] == 2
    assert any(e["reason_code"] == "timeout" for e in payload["events"])


def test_permanent_failure_not_retried_and_missing_rows_exported(
    db_engine, configuration, universe
):
    services = FakeServices(db_engine, configuration)
    services.fail_stage = "discover"
    services.retryable = False
    identifier = setup_run(db_engine, configuration, universe)
    for _ in range(2):
        asyncio.run(execute_run(db_engine, configuration, identifier, services))
    payload = finish(db_engine, identifier)
    assert (
        payload["summary"]["failed"] == 5
        and payload["summary"]["reports_discovered"] == 0
    )
    assert set(services.calls.values()) == {1}
    path = export(payload, configuration.pipeline_root)
    assert json.loads(path.read_text())["summary"]["failed"] == 5
    rows = list(csv.DictReader(path.with_suffix(".csv").open()))
    assert len(rows) == 5 and all(r["record_kind"] == "coverage" for r in rows)
    assert all("access_control" in r["failure_reasons"] for r in rows)
    assert {
        "source_url",
        "document_sha256",
        "supporting_excerpt",
        "raw_value",
        "normalised_value",
    }.issubset(rows[0])
    assert all(r["raw_value"] == "" for r in rows)
    assert export(payload, configuration.pipeline_root) != path


def test_zero_values_cannot_pass_checkpoint(db_engine, configuration, universe):
    services = FakeServices(db_engine, configuration)
    services.no_values = True
    identifier = setup_run(db_engine, configuration, universe)
    asyncio.run(execute_run(db_engine, configuration, identifier, services))
    p = finish(db_engine, identifier)
    assert p["summary"]["failed"] == 5
    assert all(c["reason_code"] == "no_source_backed_metrics" for c in p["companies"])


def test_global_lock_refuses_second_coordinator(db_engine):
    connection = batch_lock(db_engine)
    try:
        with pytest.raises(ValueError, match="Another batch"):
            batch_lock(db_engine)
    finally:
        connection.execute(text("SELECT pg_advisory_unlock_all()"))
        connection.commit()
        connection.close()


def test_recover_running_job_event_history_immutable(
    db_engine, configuration, universe
):
    identifier = setup_run(db_engine, configuration, universe)
    with Session(db_engine) as s:
        job = s.scalar(select(PipelineJob).where(PipelineJob.run_id == identifier))
    transition(db_engine, job.id, "running")
    recover(db_engine, identifier)
    assert state(db_engine, job.id).reason_code == "interrupted"
    with pytest.raises(DBAPIError), db_engine.begin() as connection:
        connection.execute(text("UPDATE pipeline_events SET status='succeeded'"))


def test_filters_and_snapshot_configuration(db_engine, configuration, universe):
    assert len(select_companies(db_engine, 5, country="gb", sector="Industrials")) == 5
    with pytest.raises(ValueError):
        select_companies(db_engine, 20, country="GB")
    selected = select_companies(db_engine, 5, companies=[UUID(universe[0]["id"])])
    assert len(selected) == 1
    assert "database_url" not in json.dumps(parameters(configuration))
    changed = configuration.model_copy(update={"llm_max_output_tokens": 2048})
    assert parameters(changed) != parameters(configuration)


def test_per_domain_slots_shared_across_instances(db_engine):
    waits = []
    DomainPacer(db_engine, ("example.com",), waits.append)("www.example.com", 2)
    DomainPacer(db_engine, ("example.com",), waits.append)("ir.example.com", 2)
    assert len(waits) == 1 and 1 < waits[0] <= 2
    DomainPacer(db_engine, ("other.com",), waits.append)("other.com", 2)
    assert len(waits) == 1


@pytest.mark.parametrize("value", ["=cmd()", "+1", "-1", "@SUM(A1)", " \t=cmd"])
def test_csv_formula_injection_escaped(value):
    assert safe_csv(value).startswith("'")


def test_schema_downgrade_refuses_existing_batch_history(
    db_engine, migration_config, configuration, universe
):
    setup_run(db_engine, configuration, universe)
    with db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="history exists"):
            command.downgrade(migration_config, "840b86a2302e")


def test_cli_20_stops_at_failed_5(db_engine, configuration, universe, monkeypatch):
    services = FakeServices(db_engine, configuration)
    services.fail_stage = "discover"
    services.retryable = False
    monkeypatch.setattr(cli, "create_extractor", lambda _: FakeExtractor([]))
    monkeypatch.setattr(cli, "Services", lambda *a: services)
    args = argparse.Namespace(
        command="run-pipeline",
        year=2025,
        observation_year=2024,
        limit=20,
        resume=False,
        run=None,
        sector=None,
        country=None,
        company=None,
        metric=["scope_1_emissions"],
        top_k=1,
    )
    assert cli.run_command(args, configuration, db_engine) == 1
    with Session(db_engine) as s:
        assert list(s.scalars(select(PipelineRun.checkpoint))) == [5]
    assert len(services.calls) == 5


def test_successful_cli_20_never_starts_50(
    db_engine, configuration, universe, monkeypatch
):
    services = FakeServices(db_engine, configuration)
    monkeypatch.setattr(cli, "create_extractor", lambda _: FakeExtractor([]))
    monkeypatch.setattr(cli, "Services", lambda *a: services)
    args = argparse.Namespace(
        command="run-pipeline",
        year=2025,
        observation_year=None,
        limit=20,
        resume=False,
        run=None,
        sector=None,
        country=None,
        company=None,
        metric=["scope_1_emissions"],
        top_k=1,
    )
    assert cli.run_command(args, configuration, db_engine) == 0
    args.resume = True
    before = services.calls.copy()
    assert (
        cli.run_command(args, configuration, db_engine) == 0
        and services.calls == before
    )
    with Session(db_engine) as s:
        assert set(s.scalars(select(PipelineRun.checkpoint))) == {5, 20}


def test_artifact_change_blocks_previously_successful_checkpoint(
    db_engine, configuration, universe
):
    services = FakeServices(db_engine, configuration)
    identifier = setup_run(db_engine, configuration, universe)
    asyncio.run(execute_run(db_engine, configuration, identifier, services))
    path = configuration.reports_root / universe[0]["id"] / "fixture.pdf"
    path.write_bytes(b"corrupt fixture")
    verify_artifacts(db_engine, configuration, identifier)
    assert finish(db_engine, identifier)["summary"]["failed"] == 1


def test_retry_limit_is_lifetime_not_per_resume(db_engine, configuration, universe):
    services = FakeServices(db_engine, configuration)
    services.fail_stage = "discover"
    settings = configuration.model_copy(update={"pipeline_job_max_attempts": 1})
    identifier = setup_run(db_engine, settings, universe)
    for _ in range(2):
        asyncio.run(execute_run(db_engine, settings, identifier, services))
    assert set(services.calls.values()) == {1}
    assert any(
        j["reason_code"] == "retry_budget_exhausted"
        for j in snapshot(db_engine, identifier)["jobs"]
    )


def test_resumed_model_calls_reuse_valid_completed_response(
    db_engine, saved_report
):  # noqa: F811
    source = FIXTURES["clean_emissions_table"]
    identifier = saved_report([source, source])
    first = FakeExtractor([[candidate(source)], ExtractionError("timeout")])
    prior = run(db_engine, identifier, first, top_k=2, resume_calls=True)
    assert prior["status"] == "failed" and len(first.calls) == 2
    second = FakeExtractor([[candidate(source, page_number=2)]])
    after = run(db_engine, identifier, second, top_k=2, resume_calls=True)
    assert after["status"] == "succeeded" and len(second.calls) == 1
    assert any(
        c.get("reused_from_run_id") == prior["run_id"]
        for c in after["summary"]["calls"]
    )


def test_fail_fast_stops_queued_companies_and_resume_never_bypasses_control(
    db_engine, configuration, universe
):
    settings = configuration.model_copy(update={"pipeline_fail_fast": True})
    services = FakeServices(db_engine, settings)
    services.fail_stage = "discover"
    services.retryable = False
    identifier = setup_run(db_engine, settings, universe)
    asyncio.run(execute_run(db_engine, settings, identifier, services))
    assert 1 <= len(services.calls) <= settings.pipeline_company_workers
    payload = finish(db_engine, identifier)
    assert payload["summary"]["failed"] == 5
    assert any(
        j["reason_code"] == "checkpoint_stopped_after_failure" for j in payload["jobs"]
    )
    before = services.calls.copy()
    asyncio.run(execute_run(db_engine, settings, identifier, services))
    assert services.calls == before


def test_cannot_create_20_without_matching_successful_5(
    db_engine, configuration, universe
):
    with pytest.raises(ValueError, match="Earlier matching"):
        setup_run(db_engine, configuration, universe, 20)
    failed = setup_run(db_engine, configuration, universe)
    with pytest.raises(ValueError, match="Earlier matching"):
        setup_run(db_engine, configuration, universe, 20, failed)


@pytest.mark.parametrize(
    "title,url",
    [
        ("Annual Sustainable Bond Report", "https://example.com/report.pdf"),
        ("Download", "https://example.com/2025-sustainable-bond-report.pdf"),
        ("Green bond impact", "https://example.com/report.pdf"),
    ],
)
def test_bond_disclosures_require_primary_source_review(title, url):
    report = Report(
        id=uuid4(), title=title, source_url=url, created_at=datetime.now(UTC)
    )
    with pytest.raises(StageFailure, match="specialised_financing_disclosure"):
        require_primary_report(report)


def test_corporate_report_not_rejected_by_specialised_source_guard():
    require_primary_report(
        Report(
            title="Sustainability Report 2025",
            source_url="https://example.com/sustainability-report-2025.pdf",
        )
    )


@pytest.mark.parametrize(
    "reviewed,pages_failed,pages_with_text,allowed",
    [
        (True, 0, 1, True),
        (False, 0, 1, False),
        (True, 1, 1, False),
        (True, 0, 0, False),
    ],
)
def test_parse_gate_requires_reviewed_decorative_pages_and_usable_text(
    db_engine,
    saved_report,
    configuration,
    monkeypatch,
    reviewed,
    pages_failed,
    pages_with_text,
    allowed,
):
    import app.pipeline.stages as stages

    report_id = saved_report(
        ["Decorative cover", "2024 Scope 1 emissions: 12 tCO2e"],
        statuses=["needs_ocr", "parsed"],
    )
    with Session(db_engine) as session, session.begin():
        page = session.scalar(
            select(DocumentPage).where(
                DocumentPage.report_id == report_id, DocumentPage.page_number == 1
            )
        )
        parse_id = page.parse_run_id
    result = {
        "run_id": str(parse_id),
        "status": "unchanged",
        "quality": {
            "parse_status": "needs_ocr",
            "pages_with_text": pages_with_text,
            "pages_failed": pages_failed,
        },
    }
    monkeypatch.setattr(stages, "parse_report", lambda *args: result)
    monkeypatch.setattr(
        stages,
        "reviewed_decorative_pages",
        lambda *args: {1: "review-id"} if reviewed else {},
    )
    service = Services(db_engine, configuration, FakeExtractor([]), IDENTITY)
    if allowed:
        receipt = asyncio.run(service.parse(report_id))
        assert receipt["visual_page_reviews"] == {"1": "review-id"}
        assert receipt["quality"]["parse_status"] == "needs_ocr"
    else:
        with pytest.raises(StageFailure):
            asyncio.run(service.parse(report_id))


@pytest.mark.parametrize("workers", [1, 2])
def test_model_semaphore_caps_simultaneous_requests(
    monkeypatch, configuration, workers
):
    import app.pipeline.stages as stages

    active = maximum = 0

    async def fake(*args, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"status": "succeeded", "run_id": str(uuid4()), "summary": {}}

    monkeypatch.setattr(stages, "extract_metric", fake)

    async def exercise():
        service = Services(
            None,
            configuration.model_copy(update={"pipeline_model_workers": workers}),
            FakeExtractor([]),
            IDENTITY,
        )
        await asyncio.gather(
            *(service.extract(uuid4(), "scope_1_emissions", 2024, 1) for _ in range(6))
        )

    asyncio.run(exercise())
    assert maximum == workers
