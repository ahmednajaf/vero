import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import main
from app.db.models import Company, MetricObservation
from app.services.company_import import import_companies, read_companies


def test_valid_seed_import_has_20_companies_and_no_metrics(db_engine, seed_csv):
    result = import_companies(seed_csv, db_engine)
    assert result.committed and result.inserted == 20 and not result.errors
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 20
        assert session.scalar(select(func.count()).select_from(MetricObservation)) == 0
        assert len(set(session.scalars(select(Company.sector)))) == 5
        samsung = session.scalar(select(Company).where(Company.ticker == "005930"))
        assert (
            samsung is not None
            and samsung.revenue is None
            and samsung.market_cap is None
        )
        assert samsung.source_row == 9 and samsung.source_sha256 == result.source_sha256


def test_reimport_is_idempotent(db_engine, seed_csv):
    import_companies(seed_csv, db_engine)
    result = import_companies(seed_csv, db_engine)
    assert (result.inserted, result.updated, result.unchanged) == (0, 0, 20)


@pytest.mark.parametrize("duplicate", ["id", "listing"])
def test_duplicate_rows_reject_entire_file(company_row, csv_file, duplicate):
    second = dict(company_row)
    if duplicate == "listing":
        second["id"] = str(uuid4())
        second["ticker"] = "exmp"
    else:
        second["ticker"] = "DIFFERENT"
    path = csv_file([company_row, second])
    engine = MagicMock()
    result = import_companies(path, engine)
    assert not result.committed
    assert result.rejected_rows == 2
    assert {error.source_row for error in result.errors} == {2, 3}
    assert all(error.code == "duplicate_in_file" for error in result.errors)
    engine.connect.assert_not_called()


def test_missing_required_field_preserves_raw_source(company_row, csv_file):
    company_row["company_name"] = "  "
    result, _ = read_companies(csv_file([company_row]))
    error = result.errors[0]
    assert error.source_row == 2 and error.field == "company_name"
    assert error.raw_values["company_name"] == "  "
    assert error.raw_cells[1] == "  "


@pytest.mark.parametrize(
    "field,value",
    [
        ("country", "ZZ"),
        ("active", "yes"),
        ("official_domain", "https://example.com"),
        ("sector", "Unknown"),
        ("id", "not-a-uuid"),
        ("reporting_year", "1999"),
        ("revenue", "NaN"),
        ("market_cap", "Infinity"),
        ("revenue", "-1"),
        ("revenue", "1.0000001"),
        ("investor_relations_url", "https://user:secret@example.com"),
        ("sustainability_url", "javascript:alert(1)"),
        ("reporting_currency", "ZZZ"),
    ],
)
def test_invalid_fields(company_row, csv_file, field, value):
    company_row[field] = value
    summary, _ = read_companies(csv_file([company_row]))
    assert summary.errors


def test_financial_amount_requires_currency_and_year(company_row, csv_file):
    company_row["revenue"] = "100"
    summary, _ = read_companies(csv_file([company_row]))
    assert "revenue_year" in summary.errors[0].message


def test_exact_decimals_zero_and_optional_nulls(db_engine, company_row, csv_file):
    company_row.update(
        revenue="123456789012345.123456",
        revenue_year="2025",
        reporting_currency="gbp",
        market_cap="0",
    )
    result = import_companies(csv_file([company_row], bom=True), db_engine)
    assert result.committed
    with Session(db_engine) as session:
        company = session.get(Company, UUID(company_row["id"]))
        assert company.revenue == Decimal("123456789012345.123456")
        assert company.market_cap == Decimal(0)
        assert company.reporting_currency == "GBP"
        assert company.sustainability_url is None


def test_update_uses_stable_id_and_preserves_created_at(
    db_engine, company_row, csv_file
):
    first_path = csv_file([company_row])
    import_companies(first_path, db_engine)
    with Session(db_engine) as session:
        original = session.get(Company, UUID(company_row["id"]))
        created_at, updated_at = original.created_at, original.updated_at
    company_row.update(
        company_name="Renamed Example plc", ticker="NEW", country="US", active="false"
    )
    result = import_companies(csv_file([company_row]), db_engine)
    assert result.committed and result.updated == 1 and result.inserted == 0
    with Session(db_engine) as session:
        company = session.get(Company, UUID(company_row["id"]))
        assert company.company_name == "Renamed Example plc" and company.ticker == "NEW"
        assert company.active is False and company.created_at == created_at
        assert company.updated_at > updated_at


def test_existing_listing_under_different_id_is_rejected(
    db_engine, company_row, csv_file
):
    import_companies(csv_file([company_row]), db_engine)
    company_row["id"] = str(uuid4())
    result = import_companies(csv_file([company_row]), db_engine)
    assert not result.committed and result.errors[0].code == "existing_listing"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1


def test_invalid_row_prevents_insert_and_update(db_engine, company_row, csv_file):
    import_companies(csv_file([company_row]), db_engine)
    changed = dict(company_row, company_name="Should not persist")
    invalid = dict(company_row, id=str(uuid4()), ticker="SECOND", country="INVALID")
    result = import_companies(csv_file([changed, invalid]), db_engine)
    assert not result.committed and result.updated == 0
    with Session(db_engine) as session:
        assert (
            session.get(Company, UUID(company_row["id"])).company_name
            == company_row["company_name"]
        )


def test_500_row_universe(db_engine, company_row, csv_file):
    rows = [
        dict(
            company_row,
            id=str(uuid4()),
            ticker=f"T{i:04}",
            company_name=f"Fixture Company {i:04}",
        )
        for i in range(500)
    ]
    result = import_companies(csv_file(rows), db_engine)
    assert result.committed and result.inserted == 500


def test_parallel_imports_are_serialised(db_engine, seed_csv):
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: import_companies(seed_csv, db_engine), range(2))
        )
    assert all(result.committed for result in results)
    assert sum(result.inserted for result in results) == 20
    assert sum(result.unchanged for result in results) == 20


def test_cli_writes_error_report_without_database(
    company_row, csv_file, tmp_path, capsys
):
    company_row["country"] = "bad"
    source = csv_file([company_row])
    report = tmp_path / "errors.json"
    assert main(["import-companies", str(source), "--report", str(report)]) == 1
    saved = json.loads(report.read_text())
    assert saved["errors"][0]["raw_values"]["country"] == "bad"
    assert saved["errors"][0]["source_row"] == 2
    assert saved["source_sha256"]
    assert "REJECTED" in capsys.readouterr().out
    before = report.read_bytes()
    assert main(["import-companies", str(source), "--report", str(report)]) == 2
    assert report.read_bytes() == before


def test_headers_and_row_width_are_checked(company_row, csv_file, tmp_path):
    bad = dict(company_row)
    bad.pop("company_name")
    summary, _ = read_companies(csv_file([bad], headers=tuple(bad)))
    assert summary.errors[0].code == "invalid_header"
    path = csv_file([company_row])
    path.write_text(path.read_text().rstrip("\n") + ",unexpected\n")
    summary, _ = read_companies(path)
    assert summary.errors[0].code == "column_count"
    assert summary.errors[0].raw_cells[-1] == "unexpected"


def test_physical_row_numbers_survive_quoted_multiline_cells(company_row, csv_file):
    first = dict(company_row, company_name="Quoted\nCompany")
    second = dict(company_row, id=str(uuid4()), ticker="SECOND", country="INVALID")
    summary, _ = read_companies(csv_file([first, second]))
    assert summary.errors[0].source_row == 4
    assert summary.errors[0].raw_values["country"] == "INVALID"


def test_empty_file_and_malformed_csv_are_rejected(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    summary, _ = read_companies(path)
    assert summary.errors[0].code == "invalid_header"
    path.write_text('"unterminated')
    summary, _ = read_companies(path)
    assert summary.errors[0].code == "invalid_csv"
