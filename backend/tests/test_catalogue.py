from collections import Counter
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalogue.contracts import Catalogue, Metric
from app.catalogue.seed import load_catalogue
from app.db.models import MetricDefinition, MetricObservation, Target

CATEGORIES = {
    "climate": 9,
    "energy": 4,
    "targets": 4,
    "water": 3,
    "waste": 3,
    "governance": 6,
    "social": 4,
    "supply_chain": 3,
    "disclosure_quality": 7,
}
CODES = {
    "scope_1_emissions",
    "scope_2_location_based",
    "scope_2_market_based",
    "scope_3_emissions",
    "scope_1_2_combined",
    "total_ghg_reported",
    "emissions_intensity",
    "base_year_emissions",
    "yoy_emissions_change",
    "total_energy_consumption",
    "electricity_consumption",
    "renewable_electricity_percent",
    "renewable_energy_percent",
    "net_zero_target_year",
    "carbon_neutral_target_year",
    "interim_emissions_target",
    "sbti_status",
    "water_withdrawal",
    "water_consumption",
    "water_discharge",
    "total_waste",
    "hazardous_waste",
    "recycled_or_diverted_percent",
    "board_sustainability_oversight",
    "executive_sustainability_owner",
    "climate_linked_remuneration",
    "tcfd_disclosure",
    "issb_disclosure",
    "assurance_status",
    "employees",
    "women_percent",
    "women_management_percent",
    "injury_rate",
    "supplier_emissions_programme",
    "scope3_supplier_engagement",
    "responsible_sourcing_policy",
    "scope1_available",
    "scope2_available",
    "scope3_available",
    "methodology_stated",
    "boundaries_stated",
    "assurance_available",
    "base_year_stated",
}


def catalogue():
    return {metric.canonical_id: metric for metric in load_catalogue().metrics}


def test_catalogue_contains_exactly_the_requested_codes_and_categories():
    seed = load_catalogue()
    assert len(seed.metrics) == 43 and set(catalogue()) == CODES
    assert Counter(m.category for m in seed.metrics) == CATEGORIES
    assert seed.catalogue_version == "1.0.0"
    assert all(m.definition_version == 1 for m in seed.metrics)
    assert len(seed.reference_sources) >= 4


def test_all_metrics_have_complete_transparent_contracts_not_company_values():
    for metric in load_catalogue().metrics:
        payload = metric.model_dump()
        assert (
            not {"company_id", "raw_value", "normalised_value", "value"}
            & payload.keys()
        )
        assert metric.aliases and metric.description and metric.comparability_warning
        assert (
            metric.normalisation_rule.version
            and metric.normalisation_rule.preserves_raw
        )
        assert metric.validation_constraints.required_context
        assert metric.validation_constraints.nullable
        assert not metric.validation_constraints.missing_is_zero
        assert not metric.validation_constraints.absence_is_false


def test_scoring_is_conditional_and_never_applies_to_targets_or_disclosures():
    metrics = catalogue()
    conditional = {
        code
        for code, metric in metrics.items()
        if metric.score_eligibility == "conditional"
    }
    assert conditional == {
        "emissions_intensity",
        "yoy_emissions_change",
        "renewable_electricity_percent",
        "renewable_energy_percent",
        "recycled_or_diverted_percent",
        "injury_rate",
    }
    assert Counter(m.score_eligibility for m in metrics.values()) == {
        "conditional": 6,
        "not_eligible": 37,
    }
    for metric in metrics.values():
        if metric.evidence_kind != "performance":
            assert (
                metric.score_eligibility == "not_eligible"
                and metric.preferred_direction is None
            )
    assert metrics["women_percent"].preferred_direction is None
    assert metrics["scope_1_emissions"].score_eligibility == "not_eligible"


def test_unit_factors_are_explicit_exact_and_dimensions_cannot_be_merged():
    metrics = catalogue()
    assert Decimal(
        metrics["scope_1_emissions"].normalisation_rule.factors_to_canonical["ktCO2e"]
    ) == Decimal("1000")
    assert Decimal(
        metrics["total_energy_consumption"].normalisation_rule.factors_to_canonical[
            "MWh"
        ]
    ) == Decimal("3.6")
    assert Decimal(
        metrics["water_consumption"].normalisation_rule.factors_to_canonical["ML"]
    ) == Decimal("1000")
    assert "gal" not in metrics["water_withdrawal"].allowed_units
    assert "ton" not in metrics["total_waste"].allowed_units
    assert "tCO2" not in metrics["scope_1_emissions"].allowed_units
    assert (
        metrics["scope_2_location_based"].scope != metrics["scope_2_market_based"].scope
    )
    assert (
        "scope2_method" in metrics["scope_1_2_combined"].required_comparison_dimensions
    )
    assert (
        "scope3_categories"
        in metrics["scope_3_emissions"].required_comparison_dimensions
    )
    assert metrics["emissions_intensity"].canonical_unit is None
    assert (
        metrics["emissions_intensity"].normalisation_rule.canonical_unit_template
        == "tCO2e/{denominator_unit}"
    )
    assert (
        "denominator_scale"
        in metrics["emissions_intensity"].required_comparison_dimensions
    )
    assert "injury_rate_type" in metrics["injury_rate"].required_comparison_dimensions


def test_percentage_levels_changes_targets_and_boolean_absence_are_distinct():
    metrics = catalogue()
    for code in (
        "women_percent",
        "women_management_percent",
        "renewable_energy_percent",
        "renewable_electricity_percent",
        "recycled_or_diverted_percent",
    ):
        assert metrics[code].validation_constraints.minimum == "0"
        assert metrics[code].validation_constraints.maximum == "100"
        assert "percentage_points" not in metrics[code].allowed_units
    assert metrics["yoy_emissions_change"].validation_constraints.minimum == "-100"
    assert metrics["yoy_emissions_change"].validation_constraints.maximum is None
    target = metrics["interim_emissions_target"]
    assert target.evidence_kind == "target" and target.data_type == "object"
    assert target.canonical_unit is None and target.validation_constraints.value_schema
    assert (
        metrics["sbti_status"].normalisation_rule.value_aliases["Committed"]
        != metrics["sbti_status"].normalisation_rule.value_aliases["Targets Set"]
    )
    assert metrics["scope2_available"].evidence_kind == "disclosure"


@pytest.mark.parametrize(
    "change",
    [
        {"allowed_units": ["not-the-canonical-unit"]},
        {"score_eligibility": "eligible"},
        {
            "score_eligibility": "conditional",
            "evidence_kind": "target",
            "preferred_direction": "lower",
        },
        {"aliases": ["same", "SAME"]},
    ],
)
def test_invalid_metric_contract_is_rejected(change):
    payload = catalogue()["scope_1_emissions"].model_dump()
    with pytest.raises(ValidationError):
        Metric.model_validate(payload | change)


def test_duplicate_canonical_ids_or_mixed_catalogue_versions_fail_validation():
    data = load_catalogue().model_dump()
    data["metrics"].append(data["metrics"][0])
    with pytest.raises(ValidationError, match="unique"):
        Catalogue.model_validate(data)
    data = load_catalogue().model_dump()
    data["metrics"][0]["catalogue_version"] = "2.0.0"
    with pytest.raises(ValidationError, match="Mixed"):
        Catalogue.model_validate(data)


def test_migration_seeds_stable_ids_once_without_any_observations(
    db_engine, migration_config
):
    with Session(db_engine) as session:
        rows = list(session.scalars(select(MetricDefinition)))
        assert len(rows) == 43 and {r.metric_code for r in rows} == CODES
        assert all(
            r.id == uuid5(NAMESPACE_URL, f"sbi:metric:{r.metric_code}:1") for r in rows
        )
        assert session.scalar(select(func.count()).select_from(MetricObservation)) == 0
        assert session.scalar(select(func.count()).select_from(Target)) == 0
    with db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        command.upgrade(migration_config, "head")
        command.check(migration_config)
        assert connection.scalar(text("SELECT count(*) FROM metric_definitions")) == 43


def test_metrics_api_matches_frozen_seed_and_includes_all_required_fields(api_client):
    response = api_client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 43 and data["category_counts"] == CATEGORIES
    assert data["score_eligibility_counts"] == {"not_eligible": 37, "conditional": 6}
    assert "not approval to rank" in data["ranking_notice"]
    seed = catalogue()
    for metric in data["items"]:
        assert {
            key: value
            for key, value in metric.items()
            if key not in {"id", "is_active"}
        } == seed[metric["canonical_id"]].model_dump(mode="json")
    assert data == api_client.get("/api/metrics").json()


def test_metrics_api_filters_and_unknown_version_do_not_fallback(api_client):
    data = api_client.get("/api/metrics?category=climate").json()
    assert data["total"] == 9 and data["category_counts"] == {"climate": 9}
    data = api_client.get("/api/metrics?score_eligibility=conditional").json()
    assert data["total"] == 6
    assert (
        api_client.get(
            "/api/metrics?category=targets&score_eligibility=conditional"
        ).json()["total"]
        == 0
    )
    assert api_client.get("/api/metrics?catalogue_version=9.0.0").json()["total"] == 0
    assert api_client.get("/api/metrics?category=unknown").status_code == 422
    assert api_client.get("/api/metrics?score_eligibility=eligible").status_code == 422


def test_catalogue_definitions_are_immutable_but_can_be_deactivated(
    db_engine, api_client
):
    for statement in (
        "UPDATE metric_definitions SET canonical_unit='kgCO2e' WHERE metric_code='scope_1_emissions'",
        "UPDATE metric_definitions SET catalogue_version=NULL WHERE metric_code='scope_1_emissions'",
        "DELETE FROM metric_definitions WHERE metric_code='scope_1_emissions'",
    ):
        with pytest.raises(IntegrityError), db_engine.begin() as connection:
            connection.execute(text(statement))
    with db_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE metric_definitions SET is_active=false WHERE metric_code='scope_1_emissions'"
            )
        )
    assert api_client.get("/api/metrics").json()["total"] == 42


@pytest.mark.parametrize(
    "change",
    [
        {"category": None},
        {"score_eligibility": "automatic"},
        {"category": "invented"},
        {
            "evidence_kind": "target",
            "score_eligibility": "conditional",
            "directionality": "lower",
        },
    ],
)
def test_database_rejects_incomplete_and_unsafe_catalogue_contracts(db_engine, change):
    with Session(db_engine) as session:
        row = session.scalar(
            select(MetricDefinition).where(
                MetricDefinition.metric_code == "scope_1_emissions"
            )
        )
        copied = {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name not in {"created_at", "updated_at"}
        }
    copied.update(id=uuid4(), metric_code="invalid_test_metric")
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        session.add(MetricDefinition(**(copied | change)))
        session.commit()


def test_new_definition_version_does_not_overwrite_old_version(db_engine):
    with Session(db_engine) as session:
        row = session.scalar(
            select(MetricDefinition).where(
                MetricDefinition.metric_code == "scope_1_emissions"
            )
        )
        copied = {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name not in {"created_at", "updated_at"}
        }
        copied.update(id=uuid4(), definition_version=2, catalogue_version="2.0.0")
        session.add(MetricDefinition(**copied))
        session.commit()
        assert (
            session.scalar(
                select(func.count())
                .select_from(MetricDefinition)
                .where(MetricDefinition.metric_code == "scope_1_emissions")
            )
            == 2
        )


def test_downgrade_refuses_to_erase_new_catalogue_versions(db_engine, migration_config):
    with Session(db_engine) as session:
        original = session.scalar(select(MetricDefinition).limit(1))
        copied = {
            column.name: getattr(original, column.name)
            for column in original.__table__.columns
            if column.name not in {"created_at", "updated_at"}
        }
        copied.update(id=uuid4(), definition_version=2, catalogue_version="2.0.0")
        session.add(MetricDefinition(**copied))
        session.commit()
    with pytest.raises(
        Exception, match="Refusing lossy catalogue downgrade"
    ), db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        command.downgrade(migration_config, "53487b8db383")
    assert "catalogue_version" in {
        c["name"] for c in inspect(db_engine).get_columns("metric_definitions")
    }


def test_seed_collision_fails_atomically_without_overwriting_existing_definition(
    db_engine, migration_config
):
    with db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        command.downgrade(migration_config, "53487b8db383")
        connection.execute(
            text(
                """INSERT INTO metric_definitions
            (id, metric_code, definition_version, name, description, sector_applicability,
             quantity_kind, canonical_unit, value_type, directionality, scope, required_comparison_dimensions)
            VALUES (:id, 'scope_1_emissions', 1, 'Existing custom definition', 'Retain this user definition',
            '[]'::jsonb, 'absolute', 'kg', 'decimal', 'context_dependent', 'custom', '[]'::jsonb)"""
            ),
            {"id": uuid4()},
        )
    with pytest.raises(IntegrityError), db_engine.begin() as connection:
        migration_config.attributes["connection"] = connection
        command.upgrade(migration_config, "head")
    with db_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "53487b8db383"
        )
        assert (
            connection.scalar(text("SELECT name FROM metric_definitions"))
            == "Existing custom definition"
        )
        assert connection.scalar(text("SELECT count(*) FROM metric_definitions")) == 1
