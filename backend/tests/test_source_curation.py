import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Report, ReportDiscoveryRun
from app.discovery.curation import register_sources
from app.services.company_import import import_companies


def manifest(tmp_path, company_row, **changes):
    row = {
        "company_id": company_row["id"],
        "requested_year": 2025,
        "detected_year": 2024,
        "title": "Example Sustainability Report 2024",
        "report_type": "sustainability",
        "source_url": "https://example.com/sustainability-report-2024.pdf",
        "discovered_from_url": "https://example.com/sustainability",
        "year_basis": "Official catalogue records publication in 2025 for performance year 2024.",
        "scope_basis": "The report covers the consolidated company's operational disclosures.",
        "reviewed_by": "test curator",
        "reviewed_at": "2026-09-30T03:21:38Z",
        **changes,
    }
    path = tmp_path / "sources.json"
    path.write_text(json.dumps([row]))
    return path


def test_curated_source_separates_years_and_is_idempotent(
    db_engine, tmp_path, company_row, csv_file
):
    import_companies(csv_file([company_row]), db_engine)
    path = manifest(tmp_path, company_row)
    config = Settings(_env_file=None)
    result = register_sources(path, db_engine, config)
    assert result[0]["status"] == "registered"
    assert register_sources(path, db_engine, config)[0]["status"] == "unchanged"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Report)) == 1
        report = session.scalar(select(Report))
        assert (report.requested_year, report.detected_year, report.reporting_year) == (
            2025,
            2024,
            None,
        )
        assert report.status == "discovered" and report.content_sha256 is None
        run = session.get(ReportDiscoveryRun, report.discovery_run_id)
        assert run.diagnostics[0]["metric_validation"] is False
        # Downloads update the human-readable selection reason. The immutable
        # source-review identity must still prevent a duplicate registration.
        run.selection_reason = "Downloaded and verified PDF MIME/signature"
        session.commit()
    repeated = register_sources(path, db_engine, config)
    assert repeated[0]["report_id"] == result[0]["report_id"]
    assert repeated[0]["status"] == "unchanged"
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Report)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"source_url": "https://mirror.example.org/sustainability-report-2024.pdf"},
        {"discovered_from_url": "https://mirror.example.org/reports"},
        {"title": "2024 Sustainable Bond Report"},
        {"title": "2024 Sustainability Policy"},
    ],
)
def test_curated_source_rejects_unofficial_and_specialised_sources(
    db_engine, tmp_path, company_row, csv_file, changes
):
    import_companies(csv_file([company_row]), db_engine)
    with pytest.raises(ValueError):
        register_sources(
            manifest(tmp_path, company_row, **changes),
            db_engine,
            Settings(_env_file=None),
        )
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Report)) == 0


def test_curated_source_rejects_duplicate_company_cycle(
    db_engine, tmp_path, company_row
):
    path = manifest(tmp_path, company_row)
    rows = json.loads(path.read_text())
    path.write_text(json.dumps(rows + rows))
    with pytest.raises(ValueError, match="Duplicate"):
        register_sources(path, db_engine, Settings(_env_file=None))


def test_curated_publisher_pdf_retains_exact_official_link(
    db_engine, tmp_path, company_row, csv_file
):
    import_companies(csv_file([company_row]), db_engine)
    url = "https://assets.ctfassets.net/company/report-2024.pdf"
    path = manifest(tmp_path, company_row, source_url=url)
    register_sources(path, db_engine, Settings(_env_file=None))
    with Session(db_engine) as session:
        report = session.scalar(select(Report))
        run = session.get(ReportDiscoveryRun, report.discovery_run_id)
        assert run.diagnostics[0]["metric_validation"] is False
        link = run.diagnostics[1]
        assert link["url"] == url
        assert link["source_page"] == "https://example.com/sustainability"
        assert link["evidence_method"] == "explicit_source_review"
        assert report.status == "discovered" and report.content_sha256 is None
