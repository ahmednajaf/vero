"""Fictional, model-free explanations; no public-company values or network."""

import csv
import io
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.benchmarking.engine import build
from app.benchmarking.contracts import Definition
from app.benchmarking.explanations import csv_export, explain
from app.catalogue.seed import load_catalogue
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app
from test_benchmarking import company, observation, performance_rows


@pytest.fixture(name="definitions")
def metric_definitions():
    return [
        Definition(
            m.canonical_id,
            m.canonical_id,
            m.definition_version,
            m.canonical_unit,
            m.evidence_kind,
            tuple(m.required_comparison_dimensions),
            m.score_eligibility,
            m.comparability_warning,
        )
        for m in load_catalogue().metrics
    ]


def scenario(definitions, values=(72, 60, 62, 64, 66, 68)):
    return build(
        [company(i) for i in range(len(values))],
        definitions,
        [
            observation(definitions, "renewable_electricity_percent", v, i)
            for i, v in enumerate(values)
        ],
        [],
        year=2025,
    )


def factor(explanation, code):
    return next(f for f in explanation["factors"] if f["metric"] == code)


@pytest.mark.parametrize(
    "subject,effect,difference",
    [
        (72, "above_peer_median", "7.000000"),
        (50, "below_peer_median", "-13.000000"),
        (64, "at_peer_median", "0.000000"),
    ],
)
def test_above_below_and_equal_median(definitions, subject, effect, difference):
    data = explain(scenario(definitions, [subject, 60, 62, 64, 66, 68]), "company-0")
    row = factor(data, "renewable_electricity_percent")
    assert row["effect"] == effect and row["difference"] == difference
    assert row["difference_unit"] == "percentage_points"
    assert row["peer_sample_size"] == 6 and row["percentile"] is not None
    assert row["score_weight"] == "0"  # electricity is not the energy score component
    assert len(row["peer_provenance"]) == 6


def test_trajectory_direction_does_not_confuse_numeric_difference_with_merit(
    definitions,
):
    rows = [
        r
        for i in range(7)
        for r in performance_rows(definitions, i, current=96 if i == 0 else 91)
    ]
    payload = build([company(i) for i in range(7)], definitions, rows, [], year=2025)
    row = factor(explain(payload, "company-0"), "derived_yoy_emissions_change")
    assert row["company_value"] == "-4.000000" and row["sector_median"] == "-9.000000"
    assert row["difference"] == "5.000000" and row["value_relation"] == "above"
    assert (
        row["effect"] == "below_peer_median" and row["preferred_direction"] == "lower"
    )
    assert row["percentile"] == "100.000000"  # not merit-adjusted
    assert row["weighted_points"] is not None


def test_missing_never_zero_and_no_peer_median_imputation(definitions):
    payload = scenario(definitions)
    row = factor(explain(payload, "company-0"), "derived_yoy_emissions_change")
    assert row["status"] == "missing_metric" and row["company_value"] is None
    assert row["sector_median"] is None and row["difference"] is None
    assert not row["completeness"]["company_complete"]


def test_not_comparable_no_invented_peer_effect(definitions):
    rows = [
        observation(definitions, "renewable_electricity_percent", 72, i)
        for i in range(6)
    ]
    rows[0] = replace(rows[0], compatibility="unchecked")
    payload = build([company(i) for i in range(6)], definitions, rows, [], year=2025)
    row = factor(explain(payload, "company-0"), "renewable_electricity_percent")
    assert row["status"] == "not_comparable" and row["company_value"] == "72.000000"
    assert row["percentile"] is None and row["sector_median"] is None
    assert row["provenance"]


def test_small_cohort_withholds_statistics(definitions):
    row = factor(
        explain(scenario(definitions, [20, 40, 60, 80]), "company-0"),
        "renewable_electricity_percent",
    )
    assert row["status"] == "insufficient_peers" and row["peer_sample_size"] == 4
    assert row["percentile"] is None and row["difference"] is None


def test_sector_stats_do_not_use_country_percentile(definitions):
    companies = [company(i, country="GB" if i == 0 else "US") for i in range(6)]
    rows = [
        observation(definitions, "renewable_electricity_percent", 50 + i, i)
        for i in range(6)
    ]
    payload = build(companies, definitions, rows, [], year=2025, peer_group="country")
    assert (
        payload["items"][0]["metrics"]["renewable_electricity_percent"]["percentile"]
        is None
    )
    row = factor(explain(payload, "company-0"), "renewable_electricity_percent")
    assert row["percentile"] == "0.000000" and row["peer_sample_size"] == 6


def context_scenario(definitions, code="scope3_available", missing_last=False):
    companies = [company(i) for i in range(8)]
    rows = [
        observation(definitions, code, None, i, raw="false" if i in {0, 6} else "true")
        for i in range(8 if not missing_last else 7)
    ]
    return build(companies, definitions, rows, [], year=2025)


def test_reviewed_scope3_absence_and_explicit_unknown_denominator(definitions):
    row = factor(
        explain(context_scenario(definitions, missing_last=True), "company-0"),
        "scope3_available",
    )
    assert row["effect"] == "disclosure_gap" and row["company_state"] == "not_reported"
    assert (
        row["peer_rate"] == "71.428571"
    )  # 5/7, not 5/6; unknown included, explicitly lower bound
    assert (
        row["completeness"]["assessed_peers"] == 6
        and row["completeness"]["unknown_peers"] == 1
    )
    assert row["completeness"]["denominator"] == 7  # subject excluded


def test_governance_prevalence_counts_assessed_comparable_peers_not_unknowns(
    definitions,
):
    row = factor(
        explain(
            context_scenario(definitions, "board_sustainability_oversight", True),
            "company-0",
        ),
        "board_sustainability_oversight",
    )
    assert row["company_value"] == "false" and row["effect"] == "context_only"
    assert row["peer_rate"] == "83.333333" and row["completeness"]["denominator"] == 6
    assert row["score_weight"] == "0"


def test_conflicting_stale_and_unreviewed_boolean_evidence_cannot_drive_prevalence(
    definitions,
):
    rows = [
        observation(definitions, "board_sustainability_oversight", None, i, raw="true")
        for i in range(6)
    ]
    rows.append(replace(rows[0], id="conflicting", raw="false"))
    rows[1] = replace(
        rows[1], provenance=rows[1].provenance | {"validation_audit_current": False}
    )
    rows[2] = replace(rows[2], compatibility="unchecked")
    payload = build([company(i) for i in range(6)], definitions, rows, [], year=2025)
    row = factor(explain(payload, "company-0"), "board_sustainability_oversight")
    assert row["company_value"] is None and row["peer_rate"] is None
    assert len(row["provenance"]) == 2


def test_common_disclosures_are_review_priorities_not_false_absence(definitions):
    companies = [company(i) for i in range(8)]
    rows = [
        observation(definitions, code, 0, i)
        for i in range(1, 7)
        for code in ("water_consumption", "recycled_or_diverted_percent")
    ]
    rows += [
        observation(definitions, "scope3_supplier_engagement", None, i, raw="false")
        for i in range(1, 7)
    ]
    payload = build(companies, definitions, rows, [], year=2025)
    data = explain(payload, "company-0")
    for row in data["disclosure_opportunities"]:
        assert row["common_gap"] and row["effect"] == "review_gap"
        assert row["company_state"] == "unknown" and row["peer_rate"] == "85.714286"
    # A reported zero is not missing; reporting 'no programme' is still a disclosure.
    assert all(
        not r["common_gap"]
        for r in explain(payload, "company-1")["disclosure_opportunities"]
    )


def test_insufficient_review_and_definition_versions_withhold_common_rates(definitions):
    rows = [observation(definitions, "water_consumption", 100, i) for i in range(1, 5)]
    payload = build([company(i) for i in range(8)], definitions, rows, [], year=2025)
    row = explain(payload, "company-0")["disclosure_opportunities"][1]
    assert row["peer_rate"] is None and row["reason"] == "insufficient_assessed_peers"
    old = next(d for d in definitions if d.code == "water_consumption")
    revised = replace(old, id="v2", version=2)
    rows += [
        replace(
            observation(definitions, "water_consumption", 100, 5), definition_id="v2"
        )
    ]
    payload = build(
        [company(i) for i in range(8)], definitions + [revised], rows, [], year=2025
    )
    assert (
        explain(payload, "company-0")["disclosure_opportunities"][1]["status"]
        == "not_comparable"
    )


def test_repeated_observations_do_not_inflate_company_counts_and_results_repeat(
    definitions,
):
    row = observation(definitions, "water_consumption", 0, 1)
    rows = [replace(row, id=f"copy-{i}") for i in range(20)]
    payload = build([company(i) for i in range(6)], definitions, rows, [], year=2025)
    data = explain(payload, "company-0")
    assert data["disclosure_opportunities"][1]["peer_sample_size"] == 1
    assert data == explain(payload, "company-0")
    assert not data["score"]["ranking_eligible"]


def test_csv_keeps_provenance_missing_fields_and_safe_text(definitions):
    payload = scenario(definitions)
    payload["items"][0]["company_name"] = '=HYPERLINK("example.com")'
    explanation = explain(payload, "company-0")
    rows = list(csv.DictReader(io.StringIO(csv_export(explanation))))
    assert len(rows) == 10 and rows[0]["company_name"].startswith("'=")
    assert rows[0]["company_value"] == "" and rows[0]["percentile"] == ""
    electricity = next(
        r for r in rows if r["metric"] == "renewable_electricity_percent"
    )
    assert len(json.loads(electricity["peer_provenance"])) == 6
    assert electricity["input_sha256"] == explanation["input_sha256"]


@pytest.fixture
def explanation_client(monkeypatch, definitions):
    payload = scenario(definitions)
    cid = "00000000-0000-4000-8000-000000000001"
    payload["items"][0]["company_id"] = cid
    monkeypatch.setattr("app.api.benchmarks.read_snapshot", lambda *_: payload)
    app = create_app(Settings(_env_file=None, app_env="test"))
    app.dependency_overrides[get_session] = lambda: SimpleNamespace(get=lambda *_: None)
    with TestClient(app) as client:
        yield client, payload, cid


def test_read_only_api_json_csv_exports_and_fingerprint(explanation_client):
    client, payload, cid = explanation_client
    url = f"/api/companies/{cid}/peer-explanation"
    response = client.get(
        url, params={"year": 2025, "expected_input_sha256": payload["input_sha256"]}
    )
    assert (
        response.status_code == 200 and response.json()["title"] == "Why this position?"
    )
    for format in ("json", "csv"):
        exported = client.get(
            url + "/export",
            params={"year": 2025, "format": format},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert exported.status_code == 200
        assert (
            exported.headers["x-explanation-sha256"]
            == response.json()["explanation_sha256"]
        )
        assert f".{format}" in exported.headers["content-disposition"]
        assert (
            "X-Explanation-SHA256" in exported.headers["access-control-expose-headers"]
        )
    assert (
        client.get(
            url, params={"year": 2025, "expected_input_sha256": "0" * 64}
        ).status_code
        == 409
    )
    assert (
        client.get(url + "/export", params={"year": 2025, "format": "pdf"}).status_code
        == 422
    )
    assert client.get(url, params={"year": 2025, "min_peers": 4}).status_code == 422
    assert (
        client.get(
            f"/api/companies/{UUID(int=9)}/peer-explanation?year=2025"
        ).status_code
        == 404
    )
