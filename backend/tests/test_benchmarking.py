"""Only fictional evidence. No model, HTTP, or real company metrics."""

from dataclasses import replace
from decimal import Decimal as D

import pytest

from app.benchmarking.contracts import (
    CompanyData,
    Definition,
    DISCLOSURES,
    EvidenceData,
)
from app.benchmarking.engine import build, percentile, revenue_band
from app.benchmarking.service import sector_summary
from app.catalogue.seed import load_catalogue


@pytest.fixture
def definitions():
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


def company(index=0, **changes):
    return replace(
        CompanyData(
            f"company-{index}",
            f"Fictional {index:03}",
            "Industrials",
            "GB",
            "Europe",
            "Industrial Equipment",
        ),
        **changes,
    )


def observation(definitions, code, value, index=0, year=2025, **changes):
    definition = next(d for d in definitions if d.code == code)
    context = {key: f"reviewed fixture {key}" for key in definition.required}
    context.update(
        reporting_year=year, period_start=f"{year}-01-01", period_end=f"{year}-12-31"
    )
    if code.startswith("scope_2_"):
        context["scope2_method"] = code.removeprefix("scope_2_")
    source = {
        "id": f"{index}:{code}:{year}",
        "report_id": f"report-{index}",
        "source_page": 2,
        "supporting_excerpt": "Fictional test fixture, not actual company data",
        "source_url": "https://example.com/fixture.pdf",
        "report_sha256": "a" * 64,
        "source_policy": "official",
        "validation_audit_current": True,
    }
    row = EvidenceData(
        source["id"],
        f"company-{index}",
        definition.id,
        year,
        "validated",
        D(str(value)) if value is not None else None,
        definition.unit,
        str(value),
        "exact",
        "comparable",
        context,
        source,
    )
    return replace(row, **changes)


def metric(payload, code, index=0):
    return payload["items"][index]["metrics"][code]


def run(definitions, rows, companies=None, **options):
    return build(companies or [company()], definitions, rows, [], year=2025, **options)


@pytest.mark.parametrize(
    "values,value,expected",
    [
        ([0, 10, 20, 30, 40], 0, 0),
        ([0, 10, 20, 30, 40], 40, 100),
        ([0, 10, 20, 30, 40], 20, 50),
        ([1, 2, 2, 2, 5], 2, 50),
        ([3, 3, 3, 3, 3], 3, 50),
    ],
)
def test_midrank_percentile(values, value, expected):
    assert percentile(D(value), list(map(D, values))) == expected


def test_percentile_small_sample_and_unknown_subject():
    assert percentile(D(1), [D(1)] * 4) is None
    assert percentile(D(2), [D(1)] * 5) is None
    with pytest.raises(ValueError):
        percentile(D(1), [D(1)] * 4, 4)


def test_medians_distance_sample_and_extremes(definitions):
    rows = [
        observation(definitions, "scope_1_emissions", v, i)
        for i, v in enumerate([0, 10, 20, 30, 40])
    ]
    result = run(definitions, rows, [company(i) for i in range(5)])
    first = metric(result, "scope_1_emissions")
    assert first["peer_sample_size"] == 5
    assert first["percentile"] == "0.000000"
    assert first["median"] == first["sector_median"] == "20.000000"
    assert first["distance_from_median"] == "-20.000000"
    assert first["flags"] == ["lowest_value"]
    assert len(first["provenance"]) == 1


@pytest.mark.parametrize(
    "dimension,value",
    [
        ("organisational_boundary", "subsidiary only"),
        ("gwp_basis", "different GWP"),
        ("period_end", "2025-06-30"),
        ("gross_or_net", "net"),
        ("methodology_version", None),
    ],
)
def test_incomparable_dimensions_not_pooled(definitions, dimension, value):
    rows = [observation(definitions, "scope_1_emissions", 100, i) for i in range(5)]
    rows[0] = replace(rows[0], context=rows[0].context | {dimension: value})
    result = run(definitions, rows, [company(i) for i in range(5)])
    assert metric(result, "scope_1_emissions", 1)["peer_sample_size"] == 4
    assert metric(result, "scope_1_emissions", 1)["percentile"] is None


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"state": "extracted"}, "missing_validated_evidence"),
        ({"state": "needs_review"}, "missing_validated_evidence"),
        ({"state": "not_comparable"}, "missing_validated_evidence"),
        ({"unit": "kgCO2e"}, "noncanonical_unit"),
        ({"qualifier": "less_than"}, "qualified_value_not_ranked"),
        ({"value": D("NaN")}, "missing_finite_normalised_value"),
        ({"value": D("-1")}, "negative_performance_value"),
        ({"compatibility": "unchecked"}, "comparability_not_reviewed"),
        ({"provenance": {}}, "source_or_validation_audit_missing"),
    ],
)
def test_quality_gates(definitions, changes, reason):
    row = replace(observation(definitions, "scope_1_emissions", 100), **changes)
    data = metric(run(definitions, [row]), "scope_1_emissions")
    assert data["eligibility_reason"] == reason
    assert data["percentile"] is None


def test_unknown_dimensions_not_guessed(definitions):
    row = observation(definitions, "scope_1_emissions", 100, context={})
    data = metric(run(definitions, [row]), "scope_1_emissions")
    assert data["eligibility_reason"].startswith("missing_comparison_dimensions:")


def test_missing_stays_null_and_checklist_unknown(definitions):
    result = run(definitions, [])
    assert metric(result, "scope_1_emissions")["value"] is None
    assert metric(result, "derived_disclosure_completeness")["value"] is None
    assert result["items"][0]["score"]["value"] is None
    assert {g["state"] for g in result["items"][0]["disclosure_gaps"]} == {"unknown"}


def test_repeated_sources_do_not_inflate_sample_and_conflicts_block(definitions):
    a = observation(definitions, "scope_1_emissions", 100)
    identical = replace(a, id="repeat", provenance=a.provenance | {"id": "repeat"})
    repeated = metric(run(definitions, [a, identical]), "scope_1_emissions")
    assert repeated["peer_sample_size"] == 1
    assert len(repeated["provenance"]) == 2
    conflict = replace(identical, value=D(101))
    data = metric(run(definitions, [a, conflict]), "scope_1_emissions")
    assert data["value"] is None
    assert data["eligibility_reason"] == "conflicting_validated_evidence"
    assert len(data["provenance"]) == 2


def test_only_validated_same_identity_successor_supersedes(definitions):
    a = observation(definitions, "scope_1_emissions", 100)
    b = replace(a, id="restated", value=D(110), supersedes=a.id)
    result = metric(run(definitions, [a, b]), "scope_1_emissions")
    assert result["value"] == "110.000000"
    assert (
        metric(
            run(definitions, [a, replace(b, state="needs_review")]), "scope_1_emissions"
        )["value"]
        == "100.000000"
    )
    assert (
        metric(
            run(
                definitions,
                [a, replace(b, company_id="company-1")],
                [company(), company(1)],
            ),
            "scope_1_emissions",
        )["value"]
        == "100.000000"
    )


def performance_rows(definitions, index=0, previous=100, current=90):
    return [
        observation(definitions, code, value, index, year)
        for year, value in [(2024, previous), (2025, current)]
        for code in ["scope_1_emissions", "scope_2_location_based"]
    ] + [observation(definitions, "renewable_energy_percent", 60, index)]


def test_derivations_and_score_reproducible(definitions):
    rows = performance_rows(definitions)
    result = run(definitions, rows)
    assert metric(result, "derived_scope_1_2_total")["value"] == "180.000000"
    assert metric(result, "derived_yoy_emissions_change")["value"] == "-10.000000"
    assert metric(result, "derived_renewable_energy_adoption")["value"] == "60.000000"
    assert result["items"][0]["score"]["value"] == "68.437500"
    assert result["items"][0]["score"]["coverage_percent"] == "80.000000"
    assert result == run(list(reversed(definitions)), list(reversed(rows)))


@pytest.mark.parametrize(
    "reason,change",
    [
        ("requires_two_comparable_years", "missing"),
        ("zero_or_invalid_prior_emissions", "zero"),
        ("year_on_year_boundary_or_method_change", "boundary"),
    ],
)
def test_yoy_unsafe_conditions(definitions, reason, change):
    rows = performance_rows(definitions, previous=0 if change == "zero" else 100)
    if change == "missing":
        rows = [r for r in rows if r.year != 2024]
    if change == "boundary":
        rows = [
            replace(r, context=r.context | {"organisational_boundary": "old perimeter"})
            if r.year == 2024
            else r
            for r in rows
        ]
    result = run(definitions, rows)
    assert (
        metric(result, "derived_yoy_emissions_change")["eligibility_reason"] == reason
    )
    assert result["items"][0]["score"]["value"] is None


def test_scope2_not_substituted_or_double_counted(definitions):
    rows = [
        observation(definitions, "scope_1_emissions", 10),
        observation(definitions, "scope_2_market_based", 20),
    ]
    assert metric(run(definitions, rows), "derived_scope_1_2_total")["value"] is None
    assert (
        metric(
            run(definitions, rows, scope2_method="market_based"),
            "derived_scope_1_2_total",
        )["value"]
        == "30.000000"
    )
    rows.append(observation(definitions, "scope_2_location_based", 25))
    assert (
        metric(run(definitions, rows), "derived_scope_1_2_total")["value"]
        == "35.000000"
    )


def test_electricity_not_substituted_for_total_energy(definitions):
    result = run(
        definitions, [observation(definitions, "renewable_electricity_percent", 100)]
    )
    assert metric(result, "derived_renewable_energy_adoption")["value"] is None
    assert result["items"][0]["score"]["value"] is None


def test_disclosure_lower_bound_not_false_absence(definitions):
    row = observation(definitions, "scope1_available", None, raw="true")
    result = run(definitions, [row])
    data = metric(result, "derived_disclosure_completeness")
    assert data["value"] == "14.285714"
    assert data["percentile"] is None
    assert result["items"][0]["score"]["components"][2]["score"] is None
    rows = [
        observation(definitions, code, None, raw="false" if i == 0 else "true")
        for i, code in enumerate(DISCLOSURES)
    ]
    result = run(definitions, rows)
    assert metric(result, "derived_disclosure_completeness")["value"] == "85.714286"
    assert result["items"][0]["disclosure_gaps"] == [
        {"metric": "scope1_available", "state": "verified_absent"}
    ]
    assert result["items"][0]["score"]["value"] is None  # disclosure alone not enough


@pytest.mark.parametrize(
    "group,change",
    [
        ("sector", {"sector": "Technology"}),
        ("country", {"country": "US"}),
        ("region", {"region": "Americas"}),
        ("industry", {"industry": "Railways"}),
        ("revenue_band", {"revenue": D("500000000")}),
    ],
)
def test_peer_filtering(definitions, group, change):
    companies = [
        company(i, revenue=D("5000000000"), revenue_year=2025, currency="GBP")
        for i in range(6)
    ]
    companies[-1] = replace(companies[-1], **change)
    result = run(
        definitions,
        [observation(definitions, "scope_1_emissions", 100 + i, i) for i in range(6)],
        companies,
        peer_group=group,
    )
    assert metric(result, "scope_1_emissions")["peer_sample_size"] == 5
    assert metric(result, "scope_1_emissions", 5)["peer_sample_size"] == 1


def test_revenue_bands_do_not_mix_currencies_or_stale_revenue():
    base = company(revenue=D("1e9"), revenue_year=2025, currency="GBP")
    assert revenue_band(base, 2025) == "GBP:2025:1bn_to_10bn"
    assert revenue_band(replace(base, revenue_year=2024), 2025) is None
    assert revenue_band(replace(base, revenue=D(0)), 2025) is None
    assert revenue_band(replace(base, currency="USD"), 2025) != revenue_band(base, 2025)


def revenue_rows(definitions):
    rows = performance_rows(definitions)
    alignment = {
        "validated": True,
        "value": "10000000",
        "currency": "GBP",
        "year": 2025,
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "organisational_boundary": rows[-1].context["organisational_boundary"],
        "currency_basis": "nominal_reported_no_fx",
        "unit_scale": "1",
        "source_url": "https://example.com/financials.pdf",
        "source_page": 3,
        "supporting_excerpt": "Fictional fixture revenue",
        "report_id": "financial-report-0",
        "report_sha256": "b" * 64,
        "source_verified": True,
    }
    return [
        replace(r, context=r.context | {"revenue_alignment": alignment})
        if r.year == 2025
        else r
        for r in rows
    ]


def test_revenue_intensity_needs_reviewed_aligned_denominator(definitions):
    companies = [
        company(revenue=D("10000000.000000"), revenue_year=2025, currency="GBP")
    ]
    result = run(definitions, revenue_rows(definitions), companies)
    data = metric(result, "derived_emissions_per_revenue")
    assert data["value"] == "18.000000" and data["unit"] == "tCO2e/million_GBP"
    assert data["provenance"][-1]["kind"] == "reviewed_revenue"
    missing = metric(
        run(definitions, performance_rows(definitions), companies),
        "derived_emissions_per_revenue",
    )
    assert (
        missing["value"] is None
        and missing["eligibility_reason"]
        == "revenue_boundary_period_and_source_not_reviewed"
    )
    mismatch = metric(
        run(
            definitions,
            revenue_rows(definitions),
            [replace(companies[0], currency="USD")],
        ),
        "derived_emissions_per_revenue",
    )
    assert (
        mismatch["value"] is None
        and mismatch["eligibility_reason"] == "revenue_denominator_mismatch"
    )


def test_sector_summary_keeps_cohorts_separate_and_flags_yoy(definitions):
    companies = [company(i) for i in range(6)]
    rows = [
        r
        for i in range(6)
        for r in performance_rows(definitions, i, current=50 + 15 * i)
    ]
    result = run(definitions, rows, companies)
    summary = sector_summary(result, "Industrials")
    assert summary["companies_total"] == 6
    assert any("biggest_yoy_decrease" in m["flags"] for m in summary["outliers"])
    assert any("biggest_yoy_increase" in m["flags"] for m in summary["outliers"])
    assert all("sample_size" in cohort for cohort in summary["cohorts"])


def test_target_years_flagged_but_not_scored(definitions):
    source = observation(definitions, "scope_1_emissions", 10).provenance
    targets = [
        source
        | {
            "id": str(i),
            "company_id": "company-0",
            "reporting_year": 2025,
            "target_year": year,
            "validation_state": "validated",
        }
        for i, year in enumerate([2020, 2050, 2100])
    ]
    result = build([company()], definitions, [], targets, year=2025)
    assert len(result["items"][0]["target_flags"]) == 2
    assert result["items"][0]["score"]["value"] is None
    assert result["items"][0]["score"]["components"][-1]["weight"] == "0"


def test_duplicate_decimal_representations_are_same_value(definitions):
    first = observation(definitions, "scope_1_emissions", "100.0")
    second = replace(first, id="another-source", value=D("100.0000"))
    data = metric(run(definitions, [first, second]), "scope_1_emissions")
    assert data["eligibility_reason"] is None
    assert data["peer_sample_size"] == 1


def test_reported_total_conflict_blocks_derived_performance(definitions):
    rows = performance_rows(definitions)
    reported = observation(definitions, "scope_1_2_combined", 250)
    reported = replace(
        reported,
        context=reported.context
        | {"scope2_method": "location_based", "included_scopes": [1, 2]},
    )
    data = metric(run(definitions, rows + [reported]), "derived_scope_1_2_total")
    assert (
        data["value"] == "180.000000"
    )  # inspectable arithmetic, withheld from comparison
    assert data["eligibility_reason"] == "reported_and_derived_total_conflict"
    assert data["percentile"] is None
    assert len(data["provenance"]) == 3


def test_mixed_component_boundaries_withhold_headline_score(definitions):
    rows = performance_rows(definitions)
    rows[-1] = replace(
        rows[-1],
        context=rows[-1].context | {"organisational_boundary": "regional subsidiary"},
    )
    score = run(definitions, rows)["items"][0]["score"]
    assert score["value"] is None
    assert score["reason"] == "component_boundaries_or_periods_differ"


def test_changed_definition_does_not_share_cohort(definitions):
    old = next(d for d in definitions if d.code == "scope_1_emissions")
    revised = replace(old, id="revised-definition", version=2)
    rows = [observation(definitions, old.code, 100, i) for i in range(5)]
    rows[-1] = replace(rows[-1], definition_id=revised.id)
    result = run(definitions + [revised], rows, [company(i) for i in range(5)])
    assert metric(result, old.code)["peer_sample_size"] == 4
    assert metric(result, old.code, 4)["peer_sample_size"] == 1


def test_increasing_sample_threshold_withholds_statistics(definitions):
    rows = [observation(definitions, "scope_1_emissions", 100, i) for i in range(5)]
    data = metric(
        run(definitions, rows, [company(i) for i in range(5)], min_peers=6),
        "scope_1_emissions",
    )
    assert data["peer_sample_size"] == 5
    assert data["percentile"] is None and data["median"] is None
    assert data["reason"] == "insufficient_comparable_peers"


def test_500_company_calculation_counts_distinct_companies(definitions):
    companies = [company(i) for i in range(500)]
    rows = [observation(definitions, "scope_1_emissions", i, i) for i in range(500)]
    result = run(definitions, rows, companies)
    assert result["total"] == 500
    assert metric(result, "scope_1_emissions")["peer_sample_size"] == 500
    assert metric(result, "scope_1_emissions")["percentile"] == "0.000000"
