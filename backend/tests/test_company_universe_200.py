"""Offline, read-only checks for the curated pilot; never import or run a pipeline."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from app.services.company_import import read_companies

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PILOT = DATA / "company_universe_200.csv"


def pilot_rows():
    summary, rows = read_companies(PILOT)
    assert summary.errors == [], summary.as_dict()
    assert summary.total_rows == 200
    return [row.company for row in rows]


def test_pilot_is_import_compatible_and_balanced():
    rows = pilot_rows()
    assert Counter(row.sector for row in rows) == {
        "Technology": 40,
        "Financial Services": 40,
        "Energy": 40,
        "Consumer / Retail": 40,
        "Industrials": 40,
    }


def test_pilot_has_unique_companies_domains_and_listings():
    rows = pilot_rows()
    assert len({row.id for row in rows}) == 200
    assert len({(row.exchange, row.ticker) for row in rows}) == 200
    assert len({row.official_domain for row in rows}) == 200
    assert len(
        {re.sub(r"\W", "", row.company_name.casefold()) for row in rows}
    ) == 200


def test_pilot_preserves_existing_seed_ids():
    seed_summary, seed = read_companies(DATA / "company_universe.csv")
    assert seed_summary.errors == []
    existing = {
        (row.company.exchange, row.company.ticker): row.company.id for row in seed
    }
    overlap = [r for r in pilot_rows() if (r.exchange, r.ticker) in existing]
    assert len(overlap) == 17
    for row in overlap:
        assert row.id == existing[row.exchange, row.ticker]


def test_pilot_country_region_and_exchange_codes():
    rows = pilot_rows()
    assert Counter(r.country for r in rows) == {
        "US": 80, "CA": 19, "JP": 18, "FR": 17, "GB": 14, "DE": 13,
        "CH": 8, "AU": 8, "NL": 7, "SE": 7, "FI": 4, "NO": 3, "DK": 2,
    }
    mics = {
        "XNAS", "XNYS", "XTSE", "XTKS", "XPAR", "XLON", "XETR",
        "XSWX", "XASX", "XAMS", "XSTO", "XHEL", "XOSL", "XCSE",
    }
    for row in rows:
        assert row.exchange in mics
        expected_region = (
            "North America" if row.country in {"US", "CA"}
            else "Asia Pacific" if row.country in {"JP", "AU"}
            else "Europe"
        )
        assert row.region == expected_region


def test_pilot_has_no_fabricated_financial_values():
    for row in pilot_rows():
        assert row.revenue is None
        assert row.revenue_year is None
        assert row.market_cap is None
        assert row.reporting_currency is None
        assert row.index is None
        assert row.reporting_year == 2025
        assert row.active is True


def test_pilot_urls_have_company_level_references():
    sources = json.loads((DATA / "company_universe_200.sources.json").read_text())
    by_id = {row["company_id"]: row for row in sources["companies"]}
    rows = pilot_rows()
    assert len(by_id) == 200
    assert set(by_id) == {str(row.id) for row in rows}
    for row in rows:
        evidence = by_id[str(row.id)]
        assert evidence["official_domain"] == row.official_domain
        assert evidence["references"]
        for url in (row.investor_relations_url, row.sustainability_url):
            if url is not None:
                assert urlsplit(url).scheme == "https"
                assert url in evidence["references"]


def test_pilot_validation_snapshot_matches_csv():
    summary = json.loads((DATA / "company_universe_200.validation.json").read_text())
    rows = pilot_rows()
    assert summary["csv_sha256"] == hashlib.sha256(PILOT.read_bytes()).hexdigest()
    assert summary["sector_counts"] == Counter(row.sector for row in rows)
    assert summary["country_counts"] == Counter(row.country for row in rows)
    assert summary["investor_relations_urls"] == sum(
        row.investor_relations_url is not None for row in rows
    )
    assert summary["sustainability_urls"] == sum(
        row.sustainability_url is not None for row in rows
    )
    assert len(summary["domain_checks"]) == 200
    assert {r["official_domain"] for r in summary["domain_checks"]} == {
        row.official_domain for row in rows
    }
    assert summary["dns_resolved"] + summary["dns_failed"] == 200
    assert summary["database_imported"] is False
    assert summary["pipeline_started"] is False
