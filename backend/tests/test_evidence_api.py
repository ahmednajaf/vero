"""Read-only evidence remains accessible without promotion to benchmark status."""

import hashlib
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MetricObservation, Report
from app.llm.contracts import ExtractionError
from test_benchmarks_api import benchmark_data  # noqa: F401

__all__ = ["benchmark_data"]  # Re-export the shared pytest fixture for collection.


def test_metric_extraction_route_keeps_call_bounded(api_client, db_engine):
    result = {
        "status": "unchanged",
        "run_id": "cached",
        "summary": {"observation_count": 1, "persisted_states": {"needs_review": 1}},
    }
    report_id = uuid4()
    with (
        patch("app.api.evidence.get_engine", return_value=db_engine),
        patch(
            "app.api.evidence.extract_metric",
            new_callable=AsyncMock,
            return_value=result,
        ) as extract,
    ):
        response = api_client.post(
            f"/api/reports/{report_id}/extract-metric",
            json={"metric": "scope_1_emissions", "observation_year": 2024},
        )
    assert response.status_code == 200
    assert response.json()["observations"] == 1
    assert response.json()["absence_established"] is False
    assert extract.call_args.args[1:4] == (report_id, "scope_1_emissions", 2024)
    assert extract.call_args.kwargs == {"top_k": 1, "resume_calls": True}


@pytest.mark.parametrize(
    "payload",
    [
        {"metric": "made_up_metric", "observation_year": 2024},
        {"metric": "net_zero_target_year", "observation_year": 2024},
        {"metric": "scope_1_emissions", "observation_year": "2024"},
        {"metric": "scope_1_emissions", "observation_year": 2024, "provider": "other"},
    ],
)
def test_metric_extraction_rejects_invalid_input_without_model_call(
    api_client, payload
):
    with patch("app.api.evidence.extract_metric", new_callable=AsyncMock) as extract:
        assert (
            api_client.post(
                f"/api/reports/{uuid4()}/extract-metric", json=payload
            ).status_code
            == 422
        )
    extract.assert_not_called()


def test_metric_extraction_provider_errors_are_safe(api_client, db_engine):
    with (
        patch("app.api.evidence.get_engine", return_value=db_engine),
        patch(
            "app.api.evidence.extract_metric",
            new_callable=AsyncMock,
            side_effect=ExtractionError("openai_timeout"),
        ),
    ):
        response = api_client.post(
            f"/api/reports/{uuid4()}/extract-metric",
            json={"metric": "scope_1_emissions", "observation_year": 2024},
        )
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "openai_timeout"}}


def test_library_counts_downloads_not_candidates(api_client, db_engine, benchmark_data):
    company_ids, observation_ids = benchmark_data
    with Session(db_engine) as session, session.begin():
        report = session.scalar(
            select(Report).where(Report.company_id == company_ids[0])
        )
        report.status = "downloaded"
        session.get(
            MetricObservation, observation_ids[0]
        ).validation_state = "needs_review"
    response = api_client.get("/api/library")
    assert response.status_code == 200
    body = response.json()
    assert body["companies_total"] == 6
    assert body["reports_downloaded"] == 1
    assert body["observations_total"] == 6
    assert body["observation_states"] == {"needs_review": 1, "validated": 5}
    assert body["pilot_companies"] == 0


def test_evidence_preserves_zero_and_review_state(
    api_client, db_engine, benchmark_data
):
    company_ids, observation_ids = benchmark_data
    with Session(db_engine) as session, session.begin():
        observation = session.get(MetricObservation, observation_ids[0])
        observation.validation_state = "needs_review"
        observation.normalised_value = None
        observation.normalised_unit = None
    body = api_client.get(f"/api/companies/{company_ids[0]}/evidence").json()
    assert len(body["observations"]) == 1
    observation = body["observations"][0]
    assert observation["raw_value"] == "0"
    assert observation["normalised_value"] is None
    assert observation["validation_state"] == "needs_review"
    assert observation["validation_audit_current"] is False
    assert observation["source_page"] == 1
    assert observation["supporting_excerpt"] == "Fictional Scope 1 evidence for tests"
    assert observation["local_report_url"] is None
    assert body["reports"] == []
    assert api_client.get(f"/api/companies/{uuid4()}/evidence").status_code == 404


def test_retained_bond_pdf_is_identified_as_non_primary(
    api_client, db_engine, benchmark_data
):
    company_ids, _ = benchmark_data
    with Session(db_engine) as session, session.begin():
        report = session.scalar(
            select(Report).where(Report.company_id == company_ids[0])
        )
        report.status = "downloaded"
        report.title = "2025 Sustainable Bond Report"
    reports = api_client.get(f"/api/companies/{company_ids[0]}/evidence").json()[
        "reports"
    ]
    assert len(reports) == 1
    assert reports[0]["primary_source_exclusion"] == "specialised_financing_disclosure"
    assert reports[0]["title"] == "2025 Sustainable Bond Report"


def test_cached_pdf_requires_safe_path_signature_and_checksum(
    api_client, db_engine, benchmark_data, tmp_path
):
    company_ids, _ = benchmark_data
    root = tmp_path / "reports"
    root.mkdir()
    content = b"%PDF-1.7\nfixture-only"
    (root / "test.pdf").write_bytes(content)
    api_client.app.state.settings = api_client.app.state.settings.model_copy(
        update={"reports_root": root}
    )
    with Session(db_engine) as session, session.begin():
        report = session.scalar(
            select(Report).where(Report.company_id == company_ids[0])
        )
        report_id = report.id
        report.status = "downloaded"
        report.storage_key = "test.pdf"
        report.content_sha256 = hashlib.sha256(content).hexdigest()
    url = f"/api/reports/{report_id}/file"
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    (root / "test.pdf").write_bytes(b"%PDF-changed")
    assert api_client.get(url).status_code == 409
    (root / "test.pdf").write_bytes(b"<html>not a PDF</html>")
    assert api_client.get(url).status_code == 409
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(content)
    for storage_key in ("../outside.pdf", str(outside)):
        with Session(db_engine) as session, session.begin():
            session.get(Report, report_id).storage_key = storage_key
        assert api_client.get(url).status_code == 404
    assert api_client.get(f"/api/reports/{uuid4()}/file").status_code == 404
