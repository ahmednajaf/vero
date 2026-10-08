from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Base,
    Company,
    DocumentChunk,
    ExtractionRun,
    MetricDefinition,
    MetricObservation,
    Report,
    ValidationEvent,
)
from app.services.company_import import import_companies


@pytest.fixture
def evidence(db_engine, company_row, csv_file):
    # Only fictional company/evidence fixtures are used for constraint tests.
    assert import_companies(csv_file([company_row]), db_engine).committed
    with Session(db_engine) as session, session.begin():
        company = session.scalar(select(Company))
        report = Report(
            company_id=company.id,
            title="Fictional fixture",
            report_type="sustainability",
            reporting_year=2025,
            source_url="https://example.com/report.pdf",
            page_count=10,
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
            physical_page_start=2,
            physical_page_end=3,
            text="Fictional test excerpt, not company data.",
            text_sha256="b" * 64,
            chunk_type="text",
            parser_name="fixture",
            parser_version="1",
        )
        metric = MetricDefinition(
            metric_code="fixture_metric",
            definition_version=1,
            name="Fixture metric",
            description="For tests only",
            sector_applicability=["Industrials"],
            quantity_kind="absolute",
            canonical_unit="t",
            value_type="decimal",
            directionality="context_dependent",
            scope="fixture",
            required_comparison_dimensions=["organisational_boundary"],
        )
        session.add_all([chunk, metric])
        session.flush()
        return dict(
            company_id=company.id,
            report_id=report.id,
            document_chunk_id=chunk.id,
            extraction_run_id=run.id,
            metric_definition_id=metric.id,
            reporting_year=2025,
            source_url=report.source_url,
            source_physical_page=2,
            supporting_excerpt=chunk.text,
            extraction_method="manual_fixture",
            confidence=Decimal("1"),
            raw_value="12",
            raw_unit="t",
            idempotency_key=uuid4().hex,
        )


def test_migration_upgrade_downgrade_and_no_metadata_drift(db_engine, migration_config):
    assert set(inspect(db_engine).get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    with db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        command.check(migration_config)
        command.downgrade(migration_config, "base")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(migration_config, "head")
        command.check(migration_config)
    assert len(inspect(db_engine).get_foreign_keys("metric_observations")) == 6


@pytest.mark.parametrize(
    "change",
    [
        {"confidence": Decimal("1.01")},
        {"confidence": None},
        {"supporting_excerpt": " "},
        {"source_physical_page": 0},
        {"source_physical_page": 4},
        {"validation_state": "invented_state"},
        {"normalised_value": Decimal("12")},
        {"validation_state": "not_reported", "raw_value": "0"},
        {"report_id": uuid4()},
    ],
)
def test_observation_integrity(db_engine, evidence, change):
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        session.add(MetricObservation(**(evidence | change)))
        session.commit()


def test_missing_is_null_not_zero(db_engine, evidence):
    evidence.update(
        validation_state="not_reported",
        raw_value=None,
        raw_unit=None,
        confidence=None,
        confidence_notes="Manual review; no model confidence",
        notes="Relevant pages reviewed",
    )
    with Session(db_engine) as session, session.begin():
        observation = MetricObservation(**evidence)
        session.add(observation)
        session.flush()
        assert observation.normalised_value is None and observation.raw_value is None


def test_report_cannot_be_attached_to_another_company(
    db_engine, evidence, company_row, csv_file
):
    company_row.update(id=str(uuid4()), ticker="OTHER")
    import_companies(csv_file([company_row]), db_engine)
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        other = session.scalar(select(Company).where(Company.ticker == "OTHER"))
        session.add(MetricObservation(**(evidence | {"company_id": other.id})))
        session.commit()


def test_validation_events_require_one_subject_and_are_append_only(db_engine, evidence):
    with Session(db_engine) as session, session.begin():
        observation = MetricObservation(**evidence)
        session.add(observation)
        session.flush()
        event = ValidationEvent(
            metric_observation_id=observation.id,
            new_state="extracted",
            actor_type="human",
            actor_reference="test-reviewer",
            reason="Fixture created",
        )
        session.add(event)
        session.flush()
        event_id = event.id
    for statement in (
        "UPDATE validation_events SET reason='changed' WHERE id=:id",
        "DELETE FROM validation_events WHERE id=:id",
    ):
        with pytest.raises(IntegrityError), db_engine.begin() as connection:
            connection.execute(text(statement), {"id": event_id})
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        session.add(
            ValidationEvent(
                new_state="extracted",
                actor_type="human",
                actor_reference="test",
                reason="No subject",
            )
        )
        session.commit()


def test_database_failure_rolls_back_all_rows_and_retains_error_row(
    db_engine, company_row, csv_file
):
    with db_engine.begin() as connection:
        connection.execute(
            text(
                """
            CREATE FUNCTION reject_fixture() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.ticker='FAIL' THEN RAISE EXCEPTION 'private connection secret'; END IF; RETURN NEW; END;
            $$
        """
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER reject_fixture BEFORE INSERT ON companies FOR EACH ROW EXECUTE FUNCTION reject_fixture()"
            )
        )
    path = csv_file([company_row, dict(company_row, id=str(uuid4()), ticker="FAIL")])
    result = import_companies(path, db_engine)
    assert not result.committed and result.inserted == 0
    assert (
        result.errors[0].source_row == 3
        and result.errors[0].raw_values["ticker"] == "FAIL"
    )
    assert "secret" not in result.errors[0].message
    with Session(db_engine) as session:
        assert session.scalar(select(Company)) is None


def test_case_insensitive_listing_constraint_in_database(
    db_engine, company_row, csv_file
):
    import_companies(csv_file([company_row]), db_engine)
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        original = session.scalar(select(Company))
        duplicate = {
            column.name: getattr(original, column.name)
            for column in Company.__table__.columns
        }
        duplicate.update(id=uuid4(), ticker="exmp", exchange="xlon")
        session.add(Company(**duplicate))
        session.commit()


def test_catalogue_downgrade_refuses_referenced_definitions(
    db_engine, evidence, migration_config
):
    with Session(db_engine) as session:
        definition = session.scalar(
            select(MetricDefinition).where(
                MetricDefinition.metric_code == "scope_1_emissions"
            )
        )
        session.add(
            MetricObservation(**(evidence | {"metric_definition_id": definition.id}))
        )
        session.commit()
    with pytest.raises(
        Exception, match="definitions are referenced by evidence"
    ), db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        command.downgrade(migration_config, "53487b8db383")
    with Session(db_engine) as session:
        assert session.scalar(select(MetricObservation)) is not None
        assert (
            session.get(
                MetricDefinition, evidence["metric_definition_id"]
            ).catalogue_version
            is None
        )


def test_legacy_metric_evidence_is_preserved_but_not_guessed_into_catalogue(
    db_engine, evidence, api_client
):
    with Session(db_engine) as session:
        legacy = session.get(MetricDefinition, evidence["metric_definition_id"])
        assert legacy.metric_code == "fixture_metric" and legacy.category is None
        assert (
            legacy.normalisation_rule is None
            and legacy.directionality == "context_dependent"
        )
    result = api_client.get("/api/metrics").json()
    assert result["total"] == 43
    assert "fixture_metric" not in {m["canonical_id"] for m in result["items"]}
