"""Acquire the explicitly selected official reports; reuse existing bytes and parsers.

Run with backend/.venv/bin/python scripts/prepare-energy-edition.py [--index].
No inference or broad company crawl. This only adds the five-company edition's sources.
"""
import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.session import create_database_engine
from app.db.models import Company, Report
from app.discovery.curation import register_sources
from app.discovery.service import download_report
from app.parsing.service import parse_report
from app.knowledge.indexing import index_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = create_database_engine(settings)
    entries = json.loads((ROOT / "data/editions/energy-2025/sources.json").read_text())
    with Session(engine) as session, session.begin():
        eni = session.scalar(select(Company).where(Company.official_domain == "eni.com"))
        if eni is None:
            session.add(Company(id=UUID(entries[-1]["company_id"]), company_name="Eni S.p.A.", ticker="ENI", exchange="XMIL", country="IT", region="Europe", sector="Energy", industry="Integrated oil and gas", official_domain="eni.com", investor_relations_url="https://www.eni.com/en-IT/investors.html", sustainability_url=entries[-1]["discovered_from_url"], reporting_currency="EUR", reporting_year=2025, active=True, source_file="data/editions/energy-2025/sources.json"))
        else:
            for entry in entries:
                if entry["company"] == "Eni S.p.A.":
                    entry["company_id"] = str(eni.id)
    for entry in entries:
        with Session(engine) as session:
            report = session.scalar(select(Report).where(Report.company_id == UUID(entry["company_id"]), Report.source_url == entry["source_url"], (Report.status == "downloaded") | Report.is_selected).order_by(Report.created_at.desc()))
            report_id = report.id if report else None
        if report_id is None:
            record = {k:v for k,v in entry.items() if k not in {"key", "company"}}
            record.update(requested_year=2025, year_basis="Official reporting hub identifies this publication; observations use the reporting period on each cited page.", scope_basis="Company-level annual or sustainability publication selected for the five-company energy edition.", reviewed_by="Vero source selection", reviewed_at=datetime.now(UTC).isoformat())
            with tempfile.TemporaryDirectory(prefix="vero-energy-sources-") as tmp:
                manifest=Path(tmp)/"sources.json"
                manifest.write_text(json.dumps([record]))
                report_id=UUID(register_sources(manifest, engine, settings)[0]["report_id"])
        with Session(engine) as session:
            report=session.get(Report,report_id)
            assert report is not None
            if report.status != "downloaded":
                company=session.get(Company,report.company_id)
                assert company is not None
                outcome=download_report(session, report, company, settings)
                print(entry["key"], outcome, flush=True)
            else:
                print(entry["key"], "reused downloaded report", report_id, flush=True)
            downloaded=report.status == "downloaded"
        if downloaded and args.index:
            print(entry["key"], parse_report(engine, report_id, settings), flush=True)
            print(entry["key"], index_report(engine, report_id, settings), flush=True)

if __name__ == "__main__":
    main()
