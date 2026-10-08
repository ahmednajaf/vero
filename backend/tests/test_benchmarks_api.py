"""PostgreSQL integration tests use isolated, disposable schemas and fictional data."""

from datetime import date
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.benchmarking.service import calculate, persist
from app.db.models import (
    BenchmarkComponent,
    BenchmarkSnapshot,
    Company,
    DocumentChunk,
    ExtractionRun,
    MetricDefinition,
    MetricObservation,
    Report,
    ValidationEvent,
)


@pytest.fixture
def benchmark_data(db_engine):
    company_ids, observation_ids = [], []
    with Session(db_engine) as session, session.begin():
        definition = session.scalar(
            select(MetricDefinition).where(
                MetricDefinition.metric_code == "scope_1_emissions"
            )
        )
        for i in range(6):
            company = Company(
                company_name=f"Fictional Benchmark {i}",
                ticker=f"FIX{i}",
                exchange="XLON",
                country="GB" if i < 5 else "US",
                region="Europe" if i < 5 else "Americas",
                sector="Industrials",
                industry="Industrial Equipment",
                official_domain=f"fixture{i}.example.com",
                reporting_year=2025,
            )
            session.add(company)
            session.flush()
            company_ids.append(company.id)
            report = Report(
                company_id=company.id,
                title="Synthetic fixture only",
                report_type="sustainability",
                reporting_year=2025,
                source_url=f"https://fixture{i}.example.com/report.pdf",
                content_sha256=str(i) * 64,
                page_count=2,
                source_policy="official",
            )
            session.add(report)
            session.flush()
            run = ExtractionRun(
                report_id=report.id,
                stage="parsing",
                idempotency_key=uuid4().hex,
                input_sha256="a" * 64,
                schema_version="test",
                code_version="test",
            )
            session.add(run)
            session.flush()
            chunk = DocumentChunk(
                report_id=report.id,
                parse_run_id=run.id,
                chunk_index=0,
                physical_page_start=1,
                physical_page_end=1,
                text="Fictional Scope 1 evidence for tests",
                text_sha256="b" * 64,
                chunk_type="text",
                parser_name="fixture",
                parser_version="1",
            )
            session.add(chunk)
            session.flush()
            extra = {
                key: f"reviewed fixture {key}"
                for key in definition.required_comparison_dimensions
            }
            observation = MetricObservation(
                company_id=company.id,
                report_id=report.id,
                document_chunk_id=chunk.id,
                metric_definition_id=definition.id,
                idempotency_key=uuid4().hex,
                reporting_year=2025,
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
                raw_value=str(i * 10),
                raw_unit="tCO2e",
                normalised_value=Decimal(i * 10),
                normalised_unit="tCO2e",
                normalisation_rule_version="fixture-v1",
                source_url=report.source_url,
                source_physical_page=1,
                supporting_excerpt=chunk.text,
                extraction_method="manual_fixture",
                confidence=Decimal(1),
                validation_state="validated",
                compatibility_state="comparable",
                organisational_boundary="consolidated group",
                consolidation_basis="operational_control",
                coverage_description="all consolidated operations",
                methodology_version="fixture-method",
                comparison_context=extra,
            )
            session.add(observation)
            session.flush()
            observation_ids.append(observation.id)
            session.add(
                ValidationEvent(
                    metric_observation_id=observation.id,
                    new_state="validated",
                    actor_type="human",
                    actor_reference="fixture-reviewer",
                    reason="Synthetic source and comparison dimensions checked",
                )
            )
    return company_ids, observation_ids


def test_benchmark_api_pagination_provenance_and_peer_filters(
    api_client, benchmark_data
):
    response = api_client.get("/api/benchmarks?year=2025&page_size=2")
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 6 and result["total_pages"] == 3
    first = result["items"][0]["metrics"]["scope_1_emissions"]
    assert first["peer_sample_size"] == 6 and first["median"] == "25.000000"
    assert first["provenance"][0]["source_page"] == 1
    assert first["provenance"][0]["report_sha256"] == "0" * 64
    assert (
        first["provenance"][0]["validation_event"]["actor_reference"]
        == "fixture-reviewer"
    )
    by_country = api_client.get(
        "/api/benchmarks?year=2025&peer_group=country&country=GB&page_size=2"
    ).json()
    assert by_country["total"] == 5
    assert (
        by_country["items"][0]["metrics"]["scope_1_emissions"]["peer_sample_size"] == 5
    )
    assert (
        by_country["items"][0]["metrics"]["scope_1_emissions"]["sector_sample_size"]
        == 6
    )
    display_only = api_client.get("/api/benchmarks?year=2025&country=US").json()
    assert display_only["total"] == 1
    assert (
        display_only["items"][0]["metrics"]["scope_1_emissions"]["peer_sample_size"]
        == 6
    )


def test_company_and_sector_routes_and_no_write(api_client, db_engine, benchmark_data):
    company_ids, _ = benchmark_data
    response = api_client.get(f"/api/companies/{company_ids[0]}/benchmark?year=2025")
    assert response.status_code == 200
    assert response.json()["company"]["company_id"] == str(company_ids[0])
    summary = api_client.get("/api/sectors/Industrials/summary?year=2025").json()
    assert summary["companies_total"] == 6
    assert summary["companies_with_score"] == 0
    cohort = next(c for c in summary["cohorts"] if c["metric"] == "scope_1_emissions")
    assert cohort["median"] == "25.000000" and cohort["sample_size"] == 6
    assert api_client.get("/api/sectors/Unknown/summary?year=2025").status_code == 404
    assert (
        api_client.get(f"/api/companies/{uuid4()}/benchmark?year=2025").status_code
        == 404
    )
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(BenchmarkSnapshot)) == 0
        assert session.scalar(select(func.count()).select_from(BenchmarkComponent)) == 0


@pytest.mark.parametrize(
    "query",
    [
        "",
        "year=1999",
        "year=2025&peer_group=invalid",
        "year=2025&min_peers=4",
        "year=2025&scope2_method=unknown",
        "year=2025&page_size=101",
        "year=2025&page=0",
    ],
)
def test_invalid_benchmark_parameters(api_client, query):
    assert api_client.get("/api/benchmarks?" + query).status_code == 422


def test_snapshot_components_idempotent_and_changed_input_new_snapshot(
    db_engine, benchmark_data
):
    company_ids, _ = benchmark_data
    with Session(db_engine) as session, session.begin():
        payload = calculate(session, year=2025)
        first = persist(session, payload)
        assert persist(session, payload) == first
        assert (
            session.scalar(select(func.count()).select_from(BenchmarkComponent)) == 30
        )
        component = session.scalar(
            select(BenchmarkComponent).where(
                BenchmarkComponent.component == "emissions_trajectory"
            )
        )
        assert component.score is None and component.reason
        snapshot = session.get(BenchmarkSnapshot, first)
        assert snapshot.results["persistence"] == "stored_snapshot"
        session.get(Company, company_ids[0]).industry = "Different industry"
        session.flush()
        second = persist(session, calculate(session, year=2025))
        assert second != first
        assert (
            session.scalar(select(func.count()).select_from(BenchmarkComponent)) == 60
        )


def test_validation_flag_without_current_audit_cannot_enter_benchmarks(
    api_client, db_engine, benchmark_data
):
    _, observation_ids = benchmark_data
    with Session(db_engine) as session, session.begin():
        # A later edit to reviewed evidence invalidates the earlier validation event.
        session.get(
            MetricObservation, observation_ids[0]
        ).coverage_description = "changed after review"
    first = api_client.get("/api/benchmarks?year=2025").json()["items"][0]["metrics"][
        "scope_1_emissions"
    ]
    assert first["eligibility_reason"] == "source_or_validation_audit_missing"
    assert first["peer_sample_size"] == 0


def test_inactive_company_not_counted(api_client, db_engine, benchmark_data):
    company_ids, _ = benchmark_data
    with Session(db_engine) as session, session.begin():
        session.get(Company, company_ids[0]).active = False
    data = api_client.get("/api/benchmarks?year=2025").json()
    assert data["total"] == 5
    assert (
        api_client.get(
            f"/api/companies/{company_ids[0]}/benchmark?year=2025"
        ).status_code
        == 409
    )


def test_review_after_update_in_same_transaction_is_current(db_engine, benchmark_data):
    _, observation_ids = benchmark_data
    with Session(db_engine) as session, session.begin():
        observation = session.get(MetricObservation, observation_ids[0])
        observation.notes = "Reviewed again after correction"
        session.flush()
        session.add(
            ValidationEvent(
                metric_observation_id=observation.id,
                previous_state="validated",
                new_state="validated",
                actor_type="human",
                actor_reference="fixture-second-review",
                reason="Rechecked source and all dimensions",
            )
        )
        session.flush()
        payload = calculate(session, year=2025)
        assert (
            payload["items"][0]["metrics"]["scope_1_emissions"]["eligibility_reason"]
            is None
        )


def test_snapshot_history_is_append_only(db_engine, benchmark_data):
    with Session(db_engine) as session, session.begin():
        snapshot_id = persist(session, calculate(session, year=2025))
    for statement in (
        "UPDATE benchmark_snapshots SET methodology_version='changed' WHERE id=:id",
        "DELETE FROM benchmark_snapshots WHERE id=:id",
        "UPDATE benchmark_components SET score=100 WHERE snapshot_id=:id",
        "DELETE FROM benchmark_components WHERE snapshot_id=:id",
    ):
        with pytest.raises(IntegrityError), db_engine.begin() as connection:
            connection.execute(text(statement), {"id": snapshot_id})


def test_report_source_edit_requires_new_review(db_engine, benchmark_data):
    _, observation_ids = benchmark_data
    with Session(db_engine) as session, session.begin():
        observation = session.get(MetricObservation, observation_ids[0])
        session.get(Report, observation.report_id).content_sha256 = "f" * 64
    with Session(db_engine) as session:
        first = calculate(session, year=2025)["items"][0]["metrics"][
            "scope_1_emissions"
        ]
        assert first["eligibility_reason"] == "source_or_validation_audit_missing"


def test_revenue_document_attestation_checked_by_adapter(db_engine, benchmark_data):
    company_ids, observation_ids = benchmark_data
    with Session(db_engine) as session, session.begin():
        company = session.get(Company, company_ids[0])
        company.revenue = Decimal("10000000")
        company.revenue_year = 2025
        company.reporting_currency = "GBP"
        scope1 = session.get(MetricObservation, observation_ids[0])
        report = session.get(Report, scope1.report_id)
        alignment = {
            "validated": True,
            "value": "10000000",
            "currency": "GBP",
            "year": 2025,
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "organisational_boundary": scope1.organisational_boundary,
            "currency_basis": "nominal",
            "unit_scale": "1",
            "report_id": str(report.id),
            "report_sha256": report.content_sha256,
            "source_url": report.source_url,
            "source_page": 1,
            "supporting_excerpt": "Synthetic consolidated revenue test fixture",
        }
        scope1.comparison_context = scope1.comparison_context | {
            "revenue_alignment": alignment
        }
        definition = session.scalar(
            select(MetricDefinition).where(
                MetricDefinition.metric_code == "scope_2_location_based"
            )
        )
        values = {
            column.name: getattr(scope1, column.name)
            for column in MetricObservation.__table__.columns
            if column.name
            not in {
                "id",
                "created_at",
                "updated_at",
                "metric_definition_id",
                "idempotency_key",
                "comparison_context",
                "raw_value",
                "normalised_value",
                "scope2_method",
            }
        }
        scope2 = MetricObservation(
            **values,
            metric_definition_id=definition.id,
            idempotency_key=uuid4().hex,
            raw_value="100",
            normalised_value=Decimal(100),
            scope2_method="location_based",
            comparison_context={
                key: f"reviewed fixture {key}"
                for key in definition.required_comparison_dimensions
            }
            | {"revenue_alignment": alignment},
        )
        session.add(scope2)
        session.flush()
        for observation in [scope1, scope2]:
            session.add(
                ValidationEvent(
                    metric_observation_id=observation.id,
                    new_state="validated",
                    actor_type="human",
                    actor_reference="financial-fixture-reviewer",
                    reason="Reviewed financial and emissions boundary alignment against recorded source",
                )
            )
        session.flush()
        payload = calculate(session, year=2025)
        intensity = payload["items"][0]["metrics"]["derived_emissions_per_revenue"]
        assert intensity["value"] == "10.000000"
        assert intensity["provenance"][-1]["source_verified"] is True
        # Claiming a verified URL for an unknown document is rejected even after
        # marking the observation reviewed; the adapter resolves the actual report.
        for observation in [scope1, scope2]:
            observation.comparison_context = observation.comparison_context | {
                "revenue_alignment": alignment
                | {"report_id": str(uuid4()), "source_verified": True}
            }
        session.flush()
        for observation in [scope1, scope2]:
            session.add(
                ValidationEvent(
                    metric_observation_id=observation.id,
                    new_state="validated",
                    actor_type="human",
                    actor_reference="fixture-reviewer",
                    reason="Invalid document reference fixture",
                )
            )
        session.flush()
        payload = calculate(session, year=2025)
        assert (
            payload["items"][0]["metrics"]["derived_emissions_per_revenue"]["value"]
            is None
        )
        assert (
            payload["items"][0]["metrics"]["scope_1_emissions"]["provenance"][0][
                "comparison_context"
            ]["revenue_alignment"]["source_verified"]
            is False
        )


def test_explicit_cli_saves_only_benchmarks(
    db_engine, benchmark_data, monkeypatch, capsys
):
    from app import cli
    from app.core.config import Settings

    monkeypatch.setattr(
        cli, "get_settings", lambda: Settings(_env_file=None, app_env="test")
    )
    monkeypatch.setattr(cli, "create_database_engine", lambda settings: db_engine)

    def forbidden(*args, **kwargs):
        pytest.fail("Benchmark command must not perform acquisition/extraction")

    monkeypatch.setattr(cli, "discover_company", forbidden)
    monkeypatch.setattr(cli, "run_pipeline", forbidden)
    monkeypatch.setattr(cli, "run_extraction", forbidden)
    assert cli.main(["build-benchmarks", "--year", "2025"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["companies"] == 6 and result["scored"] == 0
    assert result["snapshot_id"]
