import json
from pathlib import Path

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.models import Company, MetricObservation
from app.schemas.company import CompanyInput
from app.services.company_snapshot import import_snapshot


def test_real_universe_snapshot_has_identity_and_sources_not_sustainability_metrics():
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "data/company_universe_500.json").read_text())
    rows = [CompanyInput.model_validate(row) for row in data["companies"]]
    assert len(rows) == 500
    assert (
        len({r.id for r in rows}) == len({(r.exchange, r.ticker) for r in rows}) == 500
    )
    assert len({r.official_domain.removeprefix("www.") for r in rows}) == 500
    assert len({r.country for r in rows}) == 18
    assert data["metrics_added"] == 0
    assert all(r.revenue is None and r.market_cap is None for r in rows)
    for row in rows:
        evidence = data["provenance"][str(row.id)]
        if evidence["basis"] == "index_snapshot_and_company_infobox":
            assert "oldid=" in evidence["website_metadata_source"]
            assert "oldid=" in evidence["index_source"]
            assert evidence["official_websites"]
            assert "headquarters" in evidence["country_basis"]
        else:
            assert evidence["source_file"]
            # The earlier pharma importer retained its manifest name, but did
            # not store an import digest. Do not invent a historical checksum.
            if evidence["source_sha256"] is None:
                assert evidence["source_file"] == "pharma_sources.json"
                assert (root / "data" / "pharma_sources.json").is_file()
            else:
                assert len(evidence["source_sha256"]) == 64


def test_existing_company_ids_were_preserved():
    from app.services.company_import import read_companies

    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "data/company_universe_500.json").read_text())
    lookup = {r["id"]: r for r in data["companies"]}
    summary, rows = read_companies(root / "data/company_universe_200.csv")
    assert not summary.errors
    for row in rows:
        assert str(row.company.id) in lookup
        assert (
            lookup[str(row.company.id)]["official_domain"]
            == row.company.official_domain
        )


def test_complete_snapshot_can_bootstrap_database_and_resume_without_network(db_engine):
    path = Path(__file__).resolve().parents[2] / "data/company_universe_500.json"
    first = import_snapshot(path, db_engine)
    assert first["inserted"] == 500
    with Session(db_engine) as session, session.begin():
        company = session.scalar(select(Company).order_by(Company.company_name))
        identifier = company.id
        company.industry = "Operator-maintained industry"
    second = import_snapshot(path, db_engine)
    assert second["inserted"] == 0 and second["existing_preserved"] == 500
    with Session(db_engine) as session:
        assert (
            session.get(Company, identifier).industry == "Operator-maintained industry"
        )
        assert session.scalar(select(func.count()).select_from(MetricObservation)) == 0


@pytest.mark.parametrize("error", ["duplicate", "missing_provenance", "invalid_field"])
def test_bad_snapshot_is_rejected_atomically(db_engine, tmp_path, error):
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "data/company_universe_500.json").read_text())
    payload["companies"] = payload["companies"][:2]
    if error == "duplicate":
        payload["companies"].append(payload["companies"][0])
    elif error == "missing_provenance":
        payload["provenance"] = {}
    else:
        payload["companies"][1]["official_domain"] = "http://not-a-domain/"
    path = tmp_path / "companies.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        import_snapshot(path, db_engine)
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0
